from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError
from edn.operations.intake_email_preview import preview_email_schedule
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_scheduling import NOW, snapshot


@pytest.mark.parametrize(
    "change", ["cancelled", "rejected", "scope", "site", "date", "pending"]
)
def test_current_job_changes_suppress_old_email_proposals(tmp_path, change):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    draft = drafts.ingest(source)
    assert drafts.linked_job(source.identity_key, requests) is None
    job = drafts.materialise(source.identity_key, 1, requests)
    assert drafts.linked_job(source.identity_key, requests) == job
    baseline = preview_email_schedule(draft, snapshot(), now=NOW, current_job=job)
    assert baseline.start is not None
    if change in {"cancelled", "rejected"}:
        current = requests.transition(
            job.request_id, job.revision, change, reason="Synthetic decision"
        )
    elif change == "pending":
        drafts.answer(
            source.identity_key,
            1,
            "siteLocation",
            "New depot",
            actor="operator",
            requests=requests,
        )
        current = requests.get(job.request_id)
    else:
        name, value = {
            "scope": ("jobDescription", "Different scope"),
            "site": ("siteLocation", "Different depot"),
            "date": ("preferredDate", "2026-10-14"),
        }[change]
        current = requests.update(
            job.request_id, job.revision, {**job.fields, name: value}
        )
    before = (drafts.get(source.identity_key), requests.get(job.request_id))
    linked = drafts.linked_job(source.identity_key, requests)
    assert linked == current
    result = preview_email_schedule(draft, snapshot(), now=NOW, current_job=linked)
    assert result.start is None and result.reservation_key is None
    assert result.status in {"job_terminal", "job_review_required"}
    assert (drafts.get(source.identity_key), requests.get(job.request_id)) == before


def test_linked_alias_requires_canonical_review_without_mutation(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    other = requests.create(job.fields, submission_id=str(uuid4()))
    requests.resolve_duplicate(
        job.request_id,
        other.request_id,
        job.revision,
        decision="same_work",
        reason="Synthetic operator reviewed duplicate",
    )
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="canonical review"):
        drafts.linked_job(source.identity_key, requests)
    assert requests.path.read_bytes() == before
