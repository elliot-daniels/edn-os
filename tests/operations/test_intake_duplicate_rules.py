"""Pure SQLite-domain duplicate rules; no protected filesystem or platform mocks."""

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from edn.operations.intake import (
    APPROVALS_DDL,
    DDL,
    DUPLICATE_DDL,
    INTENT_DDL,
    LINKS_DDL,
    REVISIONS_DDL,
    SOURCE_DDL,
    SOURCE_HISTORY_DDL,
    SUBMISSIONS_DDL,
    IntakeError,
    IntakeStore,
    _digest,
    validate_fields,
)
from tests.operations.test_intake import fields

VARIANTS = [
    {"contactName": "ALEX SMITH"},
    {"contactName": "Alex  Smith"},
    {"company": "\uff25\uff58\uff41\uff4d\uff50\uff4c\uff45"},
    {"reference": "\uff30\uff2f\uff0d\uff11\uff12\uff13"},
    {"jobDescription": "Inspect  the network"},
    {"jobDescription": "Different wording for the same work"},
    {"urgency": "Urgent"},
]


def _domain_request(connection, original, current=None):
    request_id = str(uuid4())
    original = validate_fields(original)
    current = validate_fields(current) if current is not None else original
    revision = 2 if current != original else 1
    timestamp = "2026-10-09T00:00:00+00:00"
    actor = "local operator, uid=123"
    connection.execute(
        "INSERT INTO intake_requests VALUES (?,?,'draft','not_synced',?,?,NULL,NULL,1)",
        (request_id, revision, timestamp, timestamp),
    )
    for number, value in (
        ((1, original), (2, current)) if revision == 2 else ((1, original),)
    ):
        connection.execute(
            "INSERT INTO intake_revisions VALUES (?,?,?,'[]')",
            (request_id, number, json.dumps(value)),
        )
        connection.execute(
            "INSERT INTO intake_approvals VALUES (?,?,?,?,?,?,?,NULL)",
            (
                str(uuid4()),
                request_id,
                number,
                _digest(value, ()),
                actor,
                timestamp,
                "created" if number == 1 else "edited",
            ),
        )
    connection.execute(
        "INSERT INTO intake_submissions VALUES (?,?,'[]',?,?)",
        (str(uuid4()), json.dumps(original), _digest(original, ()), request_id),
    )
    return request_id


def _connection():
    connection = sqlite3.connect(":memory:")
    for ddl in (
        DDL,
        REVISIONS_DDL,
        APPROVALS_DDL,
        SUBMISSIONS_DDL,
        INTENT_DDL,
        SOURCE_DDL,
        SOURCE_HISTORY_DDL,
        DUPLICATE_DDL,
        LINKS_DDL,
    ):
        connection.execute(ddl)
    connection.execute("PRAGMA user_version=3")
    return connection


@pytest.mark.parametrize("changes", VARIANTS)
def test_pure_near_match_rule_flags_candidate_and_blocks_review_gate(changes):
    connection = _connection()
    try:
        first = _domain_request(connection, fields())
        second = _domain_request(connection, fields(**changes))
        requests = IntakeStore(Path("unused-domain-only.db"))
        request = requests._get(connection, second)
        assert tuple(
            item.request_id for item in requests._candidates(connection, request)
        ) == (first,)
        with pytest.raises(IntakeError, match="duplicate"):
            requests._review_gate(connection, request)
    finally:
        connection.close()


@pytest.mark.parametrize("direction", ["current", "original"])
def test_pure_current_and_original_fact_sets_both_participate(direction):
    connection = _connection()
    try:
        first = _domain_request(connection, fields())
        original = (
            fields(contactName="Alex Smth") if direction == "current" else fields()
        )
        current = (
            fields()
            if direction == "current"
            else fields(reference="Unrelated corrected value")
        )
        second = _domain_request(connection, original, current)
        requests = IntakeStore(Path("unused-domain-only.db"))
        request = requests._get(connection, second)
        assert tuple(
            item.request_id for item in requests._candidates(connection, request)
        ) == (first,)
    finally:
        connection.close()
