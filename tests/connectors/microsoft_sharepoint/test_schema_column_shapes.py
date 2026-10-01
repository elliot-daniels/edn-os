"""Offline compatibility and precise collection/record diagnostic regression tests."""

import json
from contextlib import suppress

import pytest
from test_schema_executor import FakeTransport, column, identity, responses

from edn.connectors.microsoft_sharepoint import schema_executor as m


def run_columns(tmp_path, value):
    values = responses()
    values[2] = value
    transport = FakeTransport(values)
    executor = m.SchemaExecutor(identity(), transport, m.SchemaMode.PROJECTS_DIAGNOSTIC)
    with suppress(m.SchemaInspectionError):
        executor.run(tmp_path)
    assert len(transport.calls) == 3
    return json.loads((tmp_path / m.ARTIFACT_NAME).read_text())


@pytest.mark.parametrize("count", [1, 4, 100])
def test_valid_counts(tmp_path, count):
    audit = run_columns(tmp_path, {"value": [column(i + 1) for i in range(count)]})
    assert audit["state"] == "complete"
    assert len(audit["lists"][0]["columns"]) == count
    assert audit["requests"][-1]["at_column_cap"] == (count == 100)


@pytest.mark.parametrize(
    "body,reason",
    [
        ([], "columns_top_level_not_object"),
        ({}, "columns_value_missing"),
        ({"value": None}, "columns_value_not_array"),
        ({"value": {}}, "columns_value_not_array"),
        ({"value": []}, "columns_empty"),
        ({"value": [column(i + 1) for i in range(101)]}, "columns_limit_exceeded"),
    ],
)
def test_collection_failures(tmp_path, body, reason):
    audit = run_columns(tmp_path, body)
    info = audit["requests"][-1]["diagnostic"]
    assert info["failure_reason"] == reason
    assert info["validated_records"] == 0
    assert info["column_ordinal"] is None
    assert "columns" not in audit["lists"][0]


@pytest.mark.parametrize(
    "change,reason",
    [
        (None, "column_record_not_object"),
        ({"id": None}, "column_required_field_type_invalid"),
        ({"required": None}, "column_required_field_type_invalid"),
        ({"hidden": 0}, "column_required_field_type_invalid"),
        ({"text": []}, "column_facet_shape_invalid"),
        ({"boolean": {}}, "column_type_facet_ambiguous"),
        ({"geolocation": {}}, "column_type_facet_unsupported"),
        ({"futureFacet": {"private": "SECRET"}}, "column_unexpected_shape"),
        ({"text": {"maxLength": "SECRET"}}, "column_facet_shape_invalid"),
    ],
)
@pytest.mark.parametrize("prefix", [0, 3])
def test_record_location_and_no_leak(tmp_path, change, reason, prefix):
    bad = None if change is None else dict(column(99), name="SECRET", **change)
    audit = run_columns(
        tmp_path, {"value": [column(i + 1) for i in range(prefix)] + [bad]}
    )
    info = audit["requests"][-1]["diagnostic"]
    assert info["failure_reason"] == reason
    assert info["column_ordinal"] == prefix
    assert info["validated_records"] == prefix
    assert info["stage"] == "schema_validation"
    assert "SECRET" not in json.dumps(audit)
    assert "columns" not in audit["lists"][0]


@pytest.mark.parametrize(
    "field", ["id", "name", "displayName", "hidden", "required", "readOnly"]
)
def test_missing_required(tmp_path, field):
    value = column()
    del value[field]
    audit = run_columns(tmp_path, {"value": [value]})
    assert (
        audit["requests"][-1]["diagnostic"]["failure_reason"]
        == "column_required_field_missing"
    )


FACET_EXAMPLES = {
    "text": {"maxLength": 255, "allowMultipleLines": True},
    "number": {"decimalPlaces": "automatic", "minimum": 0.5},
    "dateTime": {"displayAs": "default", "format": "dateTime"},
    "choice": {"choices": ["Synthetic"], "allowTextEntry": False},
    "boolean": {},
    "lookup": {"listId": "66944251-b9a3-40cc-9a59-05538e200c19", "columnName": "Title"},
    "personOrGroup": {"chooseFromType": "peopleOnly", "allowMultipleSelection": True},
    "currency": {"locale": "en-AU"},
    "calculated": {"outputType": "number", "formula": "SECRET"},
    "hyperlinkOrPicture": {"isPicture": False},
    "term": {"allowMultipleValues": True},
}


@pytest.mark.parametrize("kind", FACET_EXAMPLES)
def test_each_approved_facet(tmp_path, kind):
    value = column()
    value["text"] = None
    value[kind] = FACET_EXAMPLES[kind]
    audit = run_columns(tmp_path, {"value": [value]})
    assert audit["state"] == "complete"
    assert kind in audit["lists"][0]["columns"][0]
    assert "SECRET" not in json.dumps(audit)


def test_mixed_facets(tmp_path):
    values = []
    for i, (kind, facet) in enumerate(FACET_EXAMPLES.items(), 1):
        value = column(i)
        value["text"] = None
        value[kind] = facet
        values.append(value)
    assert run_columns(tmp_path, {"value": values})["state"] == "complete"


@pytest.mark.parametrize("nulls", [False, True])
def test_documented_base_only_is_explicitly_unavailable(tmp_path, nulls):
    value = column()
    del value["text"]
    value.update(hidden=True, readOnly=True)
    if nulls:
        value.update(dict.fromkeys(m.FACETS))
    audit = run_columns(tmp_path, {"value": [value]})
    assert audit["state"] == "complete"
    assert audit["lists"][0]["columns"][0]["type_status"] == "unavailable"
    assert not (audit["lists"][0]["columns"][0].keys() & m.FACETS.keys())


@pytest.mark.parametrize(
    "kind,facet",
    [
        ("lookup", {}),
        ("lookup", {"listId": "SECRET", "columnName": "Title"}),
        ("personOrGroup", {"allowMultipleSelection": "SECRET"}),
        ("choice", {"choices": "SECRET"}),
        ("calculated", {"outputType": []}),
        ("term", {"allowMultipleValues": "SECRET"}),
    ],
)
def test_malformed_metadata(tmp_path, kind, facet):
    value = column()
    value["text"] = None
    value[kind] = facet
    audit = run_columns(tmp_path, {"value": [value]})
    assert (
        audit["requests"][-1]["diagnostic"]["failure_reason"]
        == "column_facet_shape_invalid"
    )
    assert "SECRET" not in json.dumps(audit)


def test_unsolicited_top_level_discarded(tmp_path):
    audit = run_columns(tmp_path, {"value": [column()], "description": "SECRET"})
    assert audit["state"] == "complete"
    assert "SECRET" not in json.dumps(audit)
