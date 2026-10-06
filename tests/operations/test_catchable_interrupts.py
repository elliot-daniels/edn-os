"""Catchable process termination preserves incomplete, metadata-only evidence."""

import json
from dataclasses import asdict

import pytest

from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.outlook import ingest_mailbox
from tests.operations.test_import_outcomes import Pages, stores
from tests.operations.test_outlook import END, MAILBOX, NEXT, START, message


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("progress", [False, True])
def test_termination_finalizes_and_reraises_original_without_replay_loss(
    tmp_path, error_type, progress
):
    events, outcomes = stores(tmp_path)
    error = error_type("PRIVATE_SYNTHETIC_PAYLOAD")
    pages = [{"value": [message()], "@odata.nextLink": NEXT}] if progress else []
    with pytest.raises(error_type) as caught:
        ingest_mailbox(
            Pages(*pages, error), events, MAILBOX, START, END, outcomes=outcomes
        )
    assert caught.value is error
    outcome = ImportOutcomeStore(events.path, read_only=True).latest()[0]
    assert outcome.state == ("partial" if progress else "failed")
    assert outcome.finished_at is not None and outcome.reason == "import_error"
    assert outcome.inserted == outcome.pages == int(progress)
    assert "PRIVATE" not in json.dumps(asdict(outcome))
    replay = ingest_mailbox(
        Pages({"value": [message()]}), events, MAILBOX, START, END, outcomes=outcomes
    )
    assert replay.complete
    assert (replay.inserted, replay.duplicates) == (int(not progress), int(progress))
    assert len(events.list_events()) == 1
    assert outcomes.latest()[1] == outcome


def test_unfinalized_attempt_still_shows_unconfirmed_completion(tmp_path, monkeypatch):
    from edn.ui import operations

    events, outcomes = stores(tmp_path)
    outcomes.begin(MAILBOX, START, END)
    before = events.path.read_bytes()
    rendered = []
    for method in ("caption", "text", "warning"):
        monkeypatch.setattr(operations.st, method, rendered.append)
    operations.render_import_status(events.path)
    assert "In progress or interrupted" in "\n".join(rendered)
    assert outcomes.latest()[0].state == "in_progress"
    assert events.path.read_bytes() == before
