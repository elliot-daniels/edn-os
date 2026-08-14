"""Durable conservative budget authority for PA-009 provider attempts."""

from __future__ import annotations

import os
import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


class DurableBudgetError(RuntimeError):
    """Durable provider budget state is unavailable or denies admission."""


class DurablePilotBudgetLedger:
    """SQLite-backed atomic request, retry, success and spend reservations."""

    def __init__(
        self, root: Path, *, authoritative_from: datetime | None = None
    ) -> None:
        self.root = root
        self.path = root / "provider-budget.sqlite3"
        self._bootstrap_authoritative_from = authoritative_from

    def admit(
        self,
        *,
        now: datetime,
        config: object,
        input_tokens: int,
        is_retry: bool = False,
        request_id: str = "",
        attempt_number: int = 1,
    ) -> float:
        from edn.intelligence.openai_provider import (
            OPENAI_INPUT_USD_PER_MILLION,
            OPENAI_OUTPUT_USD_PER_MILLION,
            OpenAIPilotConfig,
        )

        if not isinstance(config, OpenAIPilotConfig) or now.tzinfo is None:
            raise DurableBudgetError("durable budget admission is invalid")
        estimated = (
            input_tokens / 1_000_000 * OPENAI_INPUT_USD_PER_MILLION
            + config.max_output_tokens / 1_000_000 * OPENAI_OUTPUT_USD_PER_MILLION
        )
        with closing(self._connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cutoff = datetime.fromisoformat(self._meta(connection, now))
            if now.astimezone(UTC) < cutoff:
                raise DurableBudgetError("historical provider activity is unresolved")
            day = now.astimezone(UTC).date().isoformat()
            month = day[:7]
            requests, retries, successes, daily_usd = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(is_retry),0), "
                "COALESCE(SUM(success),0), COALESCE(SUM(estimated_usd),0) "
                "FROM reservations WHERE day=?",
                (day,),
            ).fetchone()
            monthly_usd = connection.execute(
                "SELECT COALESCE(SUM(estimated_usd),0) FROM reservations WHERE month=?",
                (month,),
            ).fetchone()[0]
            if (
                requests >= config.max_requests_per_day
                or retries + int(is_retry) > config.max_retries_per_day
                or successes >= config.max_successful_briefs_per_day
                or (daily_usd + estimated) * config.usd_to_aud
                > config.max_daily_spend_aud
                or (monthly_usd + estimated) * config.usd_to_aud
                > config.max_monthly_spend_aud
            ):
                raise DurableBudgetError("durable provider budget exceeded")
            try:
                connection.execute(
                    "INSERT INTO reservations(request_id,attempt,day,month,is_retry,"
                    "estimated_usd,state,success,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        request_id,
                        attempt_number,
                        day,
                        month,
                        int(is_retry),
                        estimated,
                        "reserved",
                        0,
                        now.astimezone(UTC).isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DurableBudgetError("provider attempt replay is denied") from exc
            connection.commit()
        return estimated

    def mark_transport_started(self, request_id: str, attempt_number: int) -> None:
        self._update(request_id, attempt_number, "transport_started", success=False)

    def record_success(
        self, *, now: datetime, request_id: str = "", attempt_number: int = 1
    ) -> None:
        del now
        self._update(request_id, attempt_number, "completed", success=True)

    def _update(
        self, request_id: str, attempt: int, state: str, *, success: bool
    ) -> None:
        with closing(self._connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE reservations SET state=?, success=? "
                "WHERE request_id=? AND attempt=?",
                (state, int(success), request_id, attempt),
            ).rowcount
            if changed != 1:
                raise DurableBudgetError("durable budget reservation is missing")
            connection.commit()

    def _meta(self, connection: sqlite3.Connection, now: datetime) -> str:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key='authoritative_from'"
        ).fetchone()
        if row:
            return str(row[0])
        cutoff = self._bootstrap_authoritative_from
        if cutoff is None:
            value = now.astimezone(UTC)
            cutoff = datetime(
                value.year + (value.month == 12), value.month % 12 + 1, 1, tzinfo=UTC
            )
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES('authoritative_from',?)",
            (cutoff.astimezone(UTC).isoformat(),),
        )
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        return cutoff.astimezone(UTC).isoformat()

    def _connection(self) -> sqlite3.Connection:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_stat = self.root.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.geteuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
        ):
            raise DurableBudgetError("durable budget directory is unsafe")
        if self.path.is_symlink():
            raise DurableBudgetError("durable budget path is unsafe")
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        os.chmod(self.path, 0o600)
        file_stat = self.path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.geteuid()
            or stat.S_IMODE(file_stat.st_mode) != 0o600
        ):
            connection.close()
            raise DurableBudgetError("durable budget ownership or mode is unsafe")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS metadata("
            "key TEXT PRIMARY KEY,value TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS reservations("
            "request_id TEXT NOT NULL,attempt INTEGER NOT NULL,day TEXT NOT NULL,"
            "month TEXT NOT NULL,is_retry INTEGER NOT NULL,estimated_usd REAL NOT NULL,"
            "state TEXT NOT NULL,success INTEGER NOT NULL,created_at TEXT NOT NULL,"
            "PRIMARY KEY(request_id,attempt))"
        )
        return connection
