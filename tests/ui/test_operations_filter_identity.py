"""Reset is distinct from every persisted filter value."""

from datetime import UTC, datetime

import pytest
from streamlit.testing.v1 import AppTest

from edn.operations.models import Event
from edn.operations.storage import EventStore


@pytest.mark.parametrize(
    "field,label",
    [
        ("source", "Source"),
        ("client_id", "Client"),
        ("project_id", "Project"),
        ("job_id", "Job"),
    ],
)
def test_literal_all_is_an_exact_filter_and_reset_is_read_only(
    tmp_path, monkeypatch, field, label
):
    path = tmp_path / "events.db"
    store = EventStore(path)
    store.initialise()
    for number, value in enumerate(("All", "other", "Value: All")):
        fields = {field: value}
        source = fields.pop("source", "outlook")
        store.insert(
            Event(
                source,
                "synthetic@example.invalid",
                str(number),
                datetime.now(UTC),
                "inbound",
                "email",
                subject=value,
                **fields,
            )
        )
    before = path.read_bytes()
    monkeypatch.setenv("EDN_OPERATIONS_DB", str(path))
    app = AppTest.from_string(
        "from edn.ui.operations import render_operations_inbox\n"
        "render_operations_inbox()"
    ).run()
    assert not app.exception
    select = next(item for item in app.selectbox if item.label == label)
    assert len(select.options) == len(set(select.options))
    select.select("All").run()
    assert not app.exception
    assert [
        item.value for item in app.text if item.value in {"All", "other", "Value: All"}
    ] == ["All"]
    next(item for item in app.selectbox if item.label == label).select(
        "Value: All"
    ).run()
    assert [
        item.value for item in app.text if item.value in {"All", "other", "Value: All"}
    ] == ["Value: All"]
    next(item for item in app.selectbox if item.label == label).select(None).run()
    assert not app.exception
    assert set(
        item.value for item in app.text if item.value in {"All", "other", "Value: All"}
    ) == {"All", "other", "Value: All"}
    assert path.read_bytes() == before
