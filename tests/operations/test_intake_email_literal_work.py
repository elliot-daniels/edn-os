import json

import pytest

from edn.operations.intake_email import EmailKind, assess_email
from edn.operations.intake_email_preview import preview_email_schedule
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_scheduling import NOW, snapshot


@pytest.mark.parametrize("verb", ["replace", "install", "repair"])
def test_literal_reported_scope_site_preserves_exact_quote_and_uncertainty(verb):
    text = f"Please {verb} the failed switch at Synthetic depot."
    source = email(subject="Hello", body=text)
    result = assess_email(source)
    assert result.kind == EmailKind.NEW_JOB
    facts = {fact.field: fact for fact in result.facts}
    assert facts["jobDescription"].value == f"{verb} the failed switch"
    assert facts["siteLocation"].value == "Synthetic depot"
    assert all(
        fact.quote == text
        and fact.source_key == source.identity_key
        and fact.basis == "email_reported"
        for fact in facts.values()
    )
    assert "duration" in {question.field for question in result.questions}


@pytest.mark.parametrize(
    "text",
    [
        "Please replace the switch at Depot A or Depot B.",
        "Please replace the switch if possible at Synthetic depot.",
        "Please replace the switch at Depot A at Depot B.",
        "Please replace the switch at Synthetic\u200b depot.",
        "Please replace the switch at Depot A and Depot B.",
    ],
)
def test_ambiguous_or_unsafe_literal_keeps_scheduling_fields_unknown(text):
    result = assess_email(email(body=text))
    assert not {"jobDescription", "siteLocation"} & {
        fact.field for fact in result.facts
    }
    assert {"jobDescription", "siteLocation"} <= {
        question.field for question in result.questions
    }


def test_conflicting_literal_and_labelled_fields_require_clarification():
    result = assess_email(
        email(
            body="Site: Depot A\nScope: Replace switch\n"
            "Please repair switch at Depot B."
        )
    )
    assert not {"jobDescription", "siteLocation"} & {
        fact.field for fact in result.facts
    }


@pytest.mark.parametrize(
    "body",
    [
        "> Please replace switch at Depot.",
        "On Monday someone wrote:\nPlease replace switch at Depot.",
    ],
)
def test_quoted_history_never_becomes_current_scope(body):
    result = assess_email(email(subject="Re: New job request", body=body))
    assert result.kind == EmailKind.UNCERTAIN and not result.facts


def test_literal_source_can_prepare_canonical_job_but_duration_stays_uncertain(
    tmp_path,
):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    body = (
        BODY.replace("Scope: Replace failed switch\n", "")
        .replace("Site: Synthetic depot\n", "")
        .replace(
            "Duration: 90 minutes",
            "Please replace the failed switch at Synthetic depot.",
        )
    )
    source = email(body=body)
    retained = drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    assert job.fields["jobDescription"] == "replace the failed switch"
    assert job.fields["siteLocation"] == "Synthetic depot"
    proposal = preview_email_schedule(
        drafts.get(source.identity_key), snapshot(), now=NOW, current_job=job
    )
    assert proposal.status == "proposal_only"
    assert "Duration is an uncertain estimate" in proposal.reasons
    assert drafts.get(source.identity_key)["original"] == retained["original"]


def test_version_four_retained_assessment_requires_audited_synthetic_upgrade(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    retained = drafts.ingest(source)
    legacy = dict(retained["assessment"], version=4)
    with drafts._backend._connect() as connection:
        connection.execute(
            "UPDATE email_drafts SET assessment=? WHERE source_key=?",
            (json.dumps(legacy), source.identity_key),
        )
    before = drafts._backend.path.read_bytes()
    old = drafts.get(source.identity_key)
    assert old["assessment_stale"] is True and old["revision"] == 1
    assert drafts._backend.path.read_bytes() == before
    from edn.operations.intake import IntakeError

    with pytest.raises(IntakeError):
        drafts.materialise(source.identity_key, 1, requests)
    current = drafts.reassess_synthetic(source.identity_key, 1, actor="local-operator")
    assert current["assessment"]["version"] == 5 and current["revision"] == 2
    assert current["original"] == retained["original"]
    assert current["history"][-1]["previous_assessment"] == legacy
    assert (
        drafts.reassess_synthetic(source.identity_key, 2, actor="local-operator")
        == current
    )
    assert (
        drafts.materialise(source.identity_key, 2, requests).fields["siteLocation"]
        == "Synthetic depot"
    )
