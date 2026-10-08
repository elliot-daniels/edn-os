"""Durable single-operator intent and atomic same-key request receipt."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, IntakeStore
from tests.operations.test_intake import fields, store


def test_lost_response_restart_receipt_and_replay_after_review_edits(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    intent = requests.begin_submission()
    assert intent.fields is None and intent.request_id is None
    first = requests.create(fields(), submission_id=intent.submission_id)
    reopened = IntakeStore(requests.path)
    restored = reopened.current_submission()
    assert restored.submission_id == intent.submission_id
    assert restored.request_id == first.request_id and restored.fields == first.fields
    reopened.update(first.request_id, 1, fields(reference="corrected"))
    replay = reopened.create(fields(), submission_id=intent.submission_id)
    assert replay.request_id == first.request_id and replay.revision == 2
    assert replay.fields["reference"] == "corrected"
    assert len(reopened.list_requests()) == 1
    assert reopened.current_submission() == restored
    next_intent = reopened.begin_submission()
    assert next_intent.submission_id != intent.submission_id
    second = reopened.create(fields(), submission_id=next_intent.submission_id)
    assert second.request_id != first.request_id
    assert len(reopened.list_requests()) == 2


def test_changed_initial_facts_conflict_without_mutation(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    key = str(uuid4())
    request = requests.create(fields(), submission_id=key)
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="original facts"):
        requests.create(fields(reference="changed"), submission_id=key)
    assert requests.path.read_bytes() == before
    assert requests.get(request.request_id) == request


def test_concurrent_same_key_single_request_receipt_and_no_revision_growth(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(
            workers.map(
                lambda _: IntakeStore(requests.path).create(
                    fields(), submission_id=key
                ),
                range(8),
            )
        )
    assert len({request.request_id for request in results}) == 1
    assert {request.revision for request in results} == {1}
    assert len(requests.list_requests()) == 1


def test_read_only_intent_refusal_and_invalid_keys(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError):
        IntakeStore(requests.path, read_only=True).begin_submission()
    with pytest.raises(IntakeError):
        requests.create(fields(), submission_id="bad-key")
    assert requests.path.read_bytes() == before
