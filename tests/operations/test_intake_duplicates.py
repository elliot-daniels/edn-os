"""Normalised possible-work signal never replaces stable request identity."""

from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, _duplicate_fingerprint
from tests.operations.test_intake import fields, store
from tests.operations.test_intake_source import contract, identity

VARIANTS = [
    {"contactName": "ALEX SMITH"},
    {"contactName": "Alex  Smith"},
    {"company": "\uff25\uff58\uff41\uff4d\uff50\uff4c\uff45"},
    {"reference": "\uff30\uff2f\uff0d\uff11\uff12\uff13"},
    {"jobDescription": "Inspect  the network"},
    {"jobDescription": "Different wording for the same intended work"},
    {"urgency": "Urgent"},
    {"jobDescription": "Different wording", "urgency": "Time-sensitive"},
]


@pytest.mark.parametrize("changes", VARIANTS)
def test_identifying_fingerprint_normalises_compatibility_case_and_space(changes):
    assert _duplicate_fingerprint(fields(**changes)) == _duplicate_fingerprint(fields())


@pytest.mark.parametrize(
    "field,value",
    [
        ("company", "Different company"),
        ("contactName", "Different person"),
        ("siteLocation", "Different site"),
        ("reference", "Different reference"),
        ("preferredDate", "2026-10-10"),
    ],
)
def test_identifying_fact_changes_have_different_possible_work_signal(field, value):
    assert _duplicate_fingerprint(fields(**{field: value})) != _duplicate_fingerprint(
        fields()
    )


@pytest.mark.parametrize("changes", VARIANTS)
def test_near_manual_import_match_blocks_approval_until_reasoned_decision(
    tmp_path, changes
):
    requests = store(tmp_path)
    if requests is None:
        return
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    manual = requests.create(fields(**changes), submission_id=str(uuid4()))
    assert requests.duplicate_candidates(manual.request_id) == (imported,)
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="duplicate"):
        requests.approve(manual.request_id, 1)
    assert requests.path.read_bytes() == before
    requests.resolve_duplicate(
        manual.request_id,
        imported.request_id,
        1,
        decision="distinct",
        reason="Operator confirmed separate work despite similar identifying facts",
    )
    requests.approve(manual.request_id, 1)
    assert len(requests.list_requests()) == 2


def test_corrected_current_facts_and_preserved_original_facts_both_detect_matches(
    tmp_path,
):
    requests = store(tmp_path)
    if requests is None:
        return
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    manual = requests.create(
        fields(contactName="Alex Smth"), submission_id=str(uuid4())
    )
    assert requests.duplicate_candidates(manual.request_id) == ()
    corrected = requests.update(manual.request_id, 1, fields())
    assert requests.duplicate_candidates(corrected.request_id) == (imported,)
    with pytest.raises(IntakeError, match="duplicate"):
        requests.approve(corrected.request_id, corrected.revision)
    original_match = requests.create(
        fields(reference="\uff30\uff2f\uff0d\uff11\uff12\uff13"),
        submission_id=str(uuid4()),
    )
    moved = requests.update(
        original_match.request_id, 1, fields(reference="New unrelated reference")
    )
    candidates = {
        item.request_id for item in requests.duplicate_candidates(moved.request_id)
    }
    assert imported.request_id in candidates
    with pytest.raises(IntakeError, match="duplicate"):
        requests.approve(moved.request_id, moved.revision)


def test_distinct_decision_stays_revision_and_full_content_hash_bound(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    manual = requests.create(
        fields(contactName="ALEX SMITH"), submission_id=str(uuid4())
    )
    requests.resolve_duplicate(
        manual.request_id,
        imported.request_id,
        1,
        decision="distinct",
        reason="Two independent jobs confirmed",
    )
    assert requests.duplicate_candidates(manual.request_id) == ()
    changed = requests.update(
        manual.request_id,
        1,
        fields(
            contactName="ALEX SMITH",
            jobDescription="Changed description after resolution",
        ),
    )
    assert requests.duplicate_candidates(changed.request_id) == (imported,)
    with pytest.raises(IntakeError, match="duplicate"):
        requests.approve(changed.request_id, changed.revision)
    requests.resolve_duplicate(
        changed.request_id,
        imported.request_id,
        changed.revision,
        decision="distinct",
        reason="Reconfirm distinct work after corrected details",
    )
    requests.approve(changed.request_id, changed.revision)
