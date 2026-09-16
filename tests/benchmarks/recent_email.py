"""Synthetic-only benchmark; creates and removes its own temporary database.

PYTHONPATH=src python tests/benchmarks/recent_email.py
No business mailbox or existing database is opened.
"""

import json
import sqlite3
import statistics
import tempfile
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore

NOW = datetime(2026, 9, 16, tzinfo=UTC)
INDEX = (
    "CREATE INDEX IF NOT EXISTS emails_sent_instant "
    "ON emails(julianday(sent_at) DESC, source_record_key)"
)


def benchmark():
    with tempfile.TemporaryDirectory(prefix="edn-synthetic-benchmark-") as directory:
        path = Path(directory) / "synthetic.db"
        store = SQLiteEmailStore(path)
        store.initialise()
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("DROP INDEX IF EXISTS emails_sent_instant")
        for batch in range(100):
            store.add_many(
                tuple(
                    EmailRecord(
                        f"synthetic-{index:06}",
                        "Synthetic",
                        "Synthetic review",
                        "test@example.test",
                        (),
                        (),
                        (),
                        NOW - timedelta(minutes=index * 10),
                        None,
                        None,
                        "Synthetic only.",
                    )
                    for index in range(batch * 1000, (batch + 1) * 1000)
                )
            )

        def measure():
            samples = []
            for _ in range(30):
                start = time.perf_counter()
                records = store.recent(
                    since=NOW - timedelta(days=7), until=NOW, limit=10
                )
                samples.append((time.perf_counter() - start) * 1000)
                assert len(records) == 10
            return {"median_ms": statistics.median(samples), "max_ms": max(samples)}

        before = measure()
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(INDEX)
        after = measure()
        return {
            "synthetic_rows": 100000,
            "repetitions": 30,
            "before": before,
            "after": after,
            "median_speedup": before["median_ms"] / after["median_ms"],
        }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
