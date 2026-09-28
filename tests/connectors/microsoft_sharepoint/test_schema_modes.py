"""Offline proof of the explicit three-GET execution mode."""

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_schema_executor import SITE_ID, FakeTransport, http_mock, identity, responses

from edn.connectors.microsoft_sharepoint import schema_executor as m
from edn.connectors.microsoft_sharepoint import schema_launch as launch
from edn.connectors.microsoft_sharepoint.schema_plan import (
    SITE_URL,
    list_schema_requests,
)

MODE = m.SchemaMode.PROJECTS_DIAGNOSTIC


def test_three_plan_stops_and_full_remains_seven(tmp_path):
    for mode, budget in [(MODE, 3), (m.SchemaMode.FULL, 7)]:
        folder = tmp_path / mode.value
        folder.mkdir()
        transport = FakeTransport()
        path = m.SchemaExecutor(identity(), transport, mode).run(folder)
        audit = json.loads(path.read_text())
        assert len(transport.calls) == budget
        assert audit["request_budget"] == budget
        assert audit["execution_mode"] == mode.value
        assert audit["state"] == "complete"
        assert len(audit["lists"]) == (1 if budget == 3 else 3)
        assert audit["requests"][-1]["diagnostic"]["stage"] == "verified"
        assert audit["requests"][-1]["diagnostic"]["json_parsed"]


def test_sequence_cannot_generate_fourth():
    sequence = m._SchemaSequence(MODE)
    values = responses()
    operations = []
    for i in range(3):
        request = sequence.next_request
        operations.append(request.purpose)
        sequence.accept(request, values[i])
    assert operations == [
        "resolve_candidate_site",
        "verify_Projects",
        "columns_Projects",
    ]
    assert sequence.next_request is None
    assert len(sequence.plan) == 3


@pytest.mark.parametrize("target", [2, 4, "items"])
def test_real_transport_blocks_fourth_and_other_resources(monkeypatch, target):
    connection, factory = http_mock(monkeypatch)
    connection.getresponse.return_value.read.side_effect = [
        json.dumps(v).encode() for v in responses()[:3]
    ]
    transport = m.SchemaHttpTransport(lambda: "SYNTHETIC", MODE)
    sequence = m._SchemaSequence(MODE)
    for value in responses()[:3]:
        request = sequence.next_request
        transport.get(request)
        sequence.accept(request, value)
    plan = list_schema_requests(resolved_site_id=SITE_ID, resolved_web_url=SITE_URL)
    request = (
        replace(plan[0], url=plan[0].url + "/items")
        if target == "items"
        else plan[target]
    )
    with pytest.raises(m.SchemaInspectionError):
        transport.get(request)
    assert connection.request.call_count == factory.call_count == 3


@pytest.mark.parametrize("position", [0, 1, 2])
def test_failures_stop_no_retry(tmp_path, position):
    values = responses()
    values[position] = m.SchemaInspectionError("invalid_object")
    transport = FakeTransport(values)
    executor = m.SchemaExecutor(identity(), transport, MODE)
    with pytest.raises(m.SchemaInspectionError):
        executor.run(tmp_path)
    assert len(transport.calls) == position + 1
    with pytest.raises(m.SchemaInspectionError):
        executor.run(tmp_path)
    assert len(transport.calls) == position + 1
    assert (
        json.loads((tmp_path / m.ARTIFACT_NAME).read_text())["requests"][-1][
            "diagnostic"
        ]["failure_reason"]
        == "invalid_object"
    )


@pytest.mark.parametrize(
    "mode", ["projects_schema_diagnostic", 3, 7, 100, None, {}, "other"]
)
def test_untyped_or_arbitrary_mode_fails_before_work(monkeypatch, mode):
    storage = Mock()
    monkeypatch.setattr(launch, "prepare_run", storage)
    with pytest.raises(m.SchemaInspectionError, match="invalid_execution_mode"):
        launch.launch(mode)
    storage.assert_not_called()
    with pytest.raises(m.SchemaInspectionError):
        m.SchemaHttpTransport(lambda: "SECRET", mode)
    with pytest.raises(m.SchemaInspectionError):
        m.SchemaExecutor(identity(), FakeTransport(), mode)


@pytest.mark.parametrize(
    "extra",
    [
        ["--request-budget", "4"],
        ["--mode", "4"],
        ["--mo", "projects_schema_diagnostic"],
        ["--mode", "unknown"],
        ["--mode", MODE.value, "--mode=full_schema_inspection"],
    ],
)
def test_cli_cannot_expand_budget(monkeypatch, extra):
    call = Mock()
    monkeypatch.setattr(launch, "launch", call)
    monkeypatch.setattr(
        "sys.argv", ["schema_launch", "--approved-authenticate-and-inspect", *extra]
    )
    with pytest.raises(SystemExit):
        launch.main()
    call.assert_not_called()


def test_cli_passes_explicit_diagnostic_mode(monkeypatch, tmp_path):
    call = Mock(return_value=tmp_path)
    monkeypatch.setattr(launch, "launch", call)
    monkeypatch.setattr(
        "sys.argv",
        ["schema_launch", "--approved-authenticate-and-inspect", "--mode", MODE.value],
    )
    launch.main()
    call.assert_called_once_with(MODE)
