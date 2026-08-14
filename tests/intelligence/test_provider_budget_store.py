from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edn.intelligence import (
    DurableBudgetError,
    DurablePilotBudgetLedger,
    OpenAIPilotConfig,
)

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def ledger(root: Path) -> DurablePilotBudgetLedger:
    value = DurablePilotBudgetLedger(root, authoritative_from=NOW)
    if not value.path.exists():
        value.initialize_owner_opening_balance(
            cutover_at=datetime(2026, 8, 31, tzinfo=UTC),
            daily_authority_from=NOW,
            period="2026-08",
            carry_in_aud=1.0,
            monthly_limit_aud=20.0,
            authority_ref="synthetic-owner-test",
        )
    return value


def admit(
    value: DurablePilotBudgetLedger,
    request: str,
    *,
    now: datetime = NOW,
    retry: bool = False,
    attempt: int = 1,
    config: OpenAIPilotConfig | None = None,
) -> float:
    return value.admit(
        now=now,
        config=config or OpenAIPilotConfig(enabled=True),
        input_tokens=1000,
        is_retry=retry,
        request_id=request,
        attempt_number=attempt,
    )


def test_restart_persistence_two_request_retry_success_and_replay(
    tmp_path: Path,
) -> None:
    first = ledger(tmp_path)
    admit(first, "one")
    first.mark_transport_started("one", 1)
    second = ledger(tmp_path)
    admit(second, "two", retry=True, attempt=2)
    second.record_success(now=NOW, request_id="two", attempt_number=2)
    with pytest.raises(DurableBudgetError):
        admit(second, "three")
    with pytest.raises(DurableBudgetError):
        admit(second, "two", retry=True, attempt=2)


def test_daily_monthly_spend_and_rollovers(tmp_path: Path) -> None:
    config = OpenAIPilotConfig(
        enabled=True,
        max_requests_per_day=20,
        max_successful_briefs_per_day=20,
        max_retries_per_day=20,
        max_daily_spend_aud=0.007,
        max_monthly_spend_aud=0.02,
    )
    value = ledger(tmp_path)
    admit(value, "day-one", config=config)
    with pytest.raises(DurableBudgetError):
        admit(value, "day-two", config=config)
    admit(value, "next-day", now=datetime(2026, 9, 2, tzinfo=UTC), config=config)
    with pytest.raises(DurableBudgetError):
        admit(value, "month-limit", now=datetime(2026, 9, 3, tzinfo=UTC), config=config)
    admit(value, "next-month", now=datetime(2026, 10, 1, tzinfo=UTC), config=config)


def test_concurrent_admission_cannot_double_spend(tmp_path: Path) -> None:
    config = OpenAIPilotConfig(enabled=True, max_requests_per_day=1)
    ledger(tmp_path)

    def run(number: int) -> bool:
        try:
            admit(
                DurablePilotBudgetLedger(tmp_path),
                f"race-{number}",
                config=config,
            )
            return True
        except DurableBudgetError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == [False, True]


def test_crash_reservations_and_unknown_transport_remain_counted(
    tmp_path: Path,
) -> None:
    value = ledger(tmp_path)
    admit(value, "before-transport")
    admit(value, "after-start")
    value.mark_transport_started("after-start", 1)
    with pytest.raises(DurableBudgetError):
        admit(ledger(tmp_path), "after-restart")


def test_historical_activity_bootstrap_fails_closed_until_next_month(
    tmp_path: Path,
) -> None:
    value = DurablePilotBudgetLedger(tmp_path)
    with pytest.raises(DurableBudgetError):
        admit(value, "august", now=datetime(2026, 8, 14, tzinfo=UTC))


def test_owner_opening_balance_blocks_today_persists_and_rolls_month(
    tmp_path: Path,
) -> None:
    value = DurablePilotBudgetLedger(tmp_path)
    value.initialize_owner_opening_balance(
        cutover_at=datetime(2026, 8, 14, 10, tzinfo=UTC),
        daily_authority_from=datetime(2026, 8, 15, tzinfo=UTC),
        period="2026-08",
        carry_in_aud=1.0,
        monthly_limit_aud=20.0,
        authority_ref="owner-pa009-opening-balance-20260814",
    )
    with pytest.raises(DurableBudgetError, match="historical"):
        admit(value, "today", now=datetime(2026, 8, 14, 12, tzinfo=UTC))
    metadata = DurablePilotBudgetLedger(tmp_path).opening_balance()
    assert metadata["carry_in_aud"] == "1.00"
    assert metadata["historical_counters"] == "unknown_pre_ledger"
    admit(value, "tomorrow", now=datetime(2026, 8, 15, tzinfo=UTC))
    admit(value, "september", now=NOW)
    with pytest.raises(DurableBudgetError, match="already"):
        value.initialize_owner_opening_balance(
            cutover_at=datetime(2026, 8, 14, 10, tzinfo=UTC),
            daily_authority_from=datetime(2026, 8, 15, tzinfo=UTC),
            period="2026-08",
            carry_in_aud=1.0,
            monthly_limit_aud=20.0,
            authority_ref="different-authority",
        )


def test_opening_carry_is_charged_and_tampering_fails_closed(tmp_path: Path) -> None:
    value = DurablePilotBudgetLedger(tmp_path)
    value.initialize_owner_opening_balance(
        cutover_at=datetime(2026, 8, 14, 10, tzinfo=UTC),
        daily_authority_from=datetime(2026, 8, 15, tzinfo=UTC),
        period="2026-08",
        carry_in_aud=1.0,
        monthly_limit_aud=20.0,
        authority_ref="owner-pa009-opening-balance-20260814",
    )
    config = OpenAIPilotConfig(enabled=True, max_monthly_spend_aud=1.001)
    with pytest.raises(DurableBudgetError):
        admit(
            value, "carry-blocks", now=datetime(2026, 8, 15, tzinfo=UTC), config=config
        )
    connection = sqlite3.connect(value.path)
    connection.execute("UPDATE metadata SET value='0.50' WHERE key='carry_in_aud'")
    connection.commit()
    connection.close()
    with pytest.raises(DurableBudgetError, match="corrupt"):
        value.opening_balance()


def test_permissions_symlink_and_corruption_fail_closed(tmp_path: Path) -> None:
    value = ledger(tmp_path / "safe")
    admit(value, "one")
    assert (tmp_path / "safe").stat().st_mode & 0o777 == 0o700
    assert value.path.stat().st_mode & 0o777 == 0o600
    value.path.write_bytes(b"not sqlite")
    with pytest.raises((DurableBudgetError, sqlite3.DatabaseError)):
        admit(value, "two")
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "safe", target_is_directory=True)
    with pytest.raises(DurableBudgetError):
        admit(ledger(link), "linked")
