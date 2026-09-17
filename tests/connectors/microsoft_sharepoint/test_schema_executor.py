"""All transports and Graph responses are synthetic; no credentials or network."""

import json
from dataclasses import replace
from unittest.mock import Mock
from uuid import UUID

import pytest

from edn.connectors.microsoft_sharepoint import schema_executor as module
from edn.connectors.microsoft_sharepoint.schema_executor import (
    ACCOUNT,
    APPLICATION,
    ARTIFACT_NAME,
    MAX_BYTES,
    TENANT,
    SchemaExecutor,
    SchemaHttpTransport,
    SchemaIdentity,
    SchemaInspectionError,
    SchemaReply,
    validate_schema_request,
)
from edn.connectors.microsoft_sharepoint.schema_plan import (
    CANDIDATE_LISTS,
    HISTORICAL_SITE_GUID,
    HOST,
    SITE_URL,
    list_schema_requests,
    site_identity_request,
)

SITE_ID = f"{HOST},{HISTORICAL_SITE_GUID},00000000-0000-0000-0000-000000000001"


def identity():
    return SchemaIdentity(
        TENANT, APPLICATION, ACCOUNT, frozenset({"Sites.Selected"}), "synthetic-grant"
    )


def column(index=1):
    return {
        "id": str(UUID(int=index)),
        "name": f"Field{index}",
        "displayName": f"Field {index}",
        "required": False,
        "readOnly": False,
        "hidden": False,
        "text": {"maxLength": 255},
    }


def responses():
    result = [{"id": SITE_ID, "displayName": "EDN Systems", "webUrl": SITE_URL}]
    for name, identifier in CANDIDATE_LISTS:
        result.extend(
            [
                {
                    "id": identifier,
                    "displayName": name,
                    "webUrl": SITE_URL + "/Lists/" + name,
                    "list": {
                        "template": "genericList",
                        "hidden": False,
                        "contentTypesEnabled": False,
                    },
                },
                {"value": [column()]},
            ]
        )
    return result


class FakeTransport:
    def __init__(self, values=None):
        self.values = responses() if values is None else values
        self.calls = []

    def get(self, request):
        self.calls.append(request)
        value = self.values[len(self.calls) - 1]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, SchemaReply):
            return value
        return SchemaReply(200, json.dumps(value).encode())


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    monkeypatch.setattr(
        module.http.client,
        "HTTPSConnection",
        Mock(side_effect=AssertionError("Live network forbidden")),
    )


def read_artifact(path):
    return json.loads((path / ARTIFACT_NAME).read_text())


def test_happy_path_exact_seven_calls_and_audit(tmp_path, monkeypatch):
    from edn.connectors.microsoft_sharepoint.connector import (
        MicrosoftSharePointConnector,
    )

    monkeypatch.setattr(
        MicrosoftSharePointConnector,
        "__init__",
        Mock(side_effect=AssertionError("Operational connector forbidden")),
    )
    transport = FakeTransport()
    result = SchemaExecutor(identity(), transport).run(tmp_path)
    expected = (
        site_identity_request(),
        *list_schema_requests(resolved_site_id=SITE_ID, resolved_web_url=SITE_URL),
    )
    assert transport.calls == list(expected)
    artifact = read_artifact(tmp_path)
    assert result.name == ARTIFACT_NAME
    assert artifact["state"] == "complete"
    assert artifact["site"]["id"] == SITE_ID
    assert len(artifact["schema_sha256"]) == 64
    assert [r["sequence"] for r in artifact["requests"]] == list(range(1, 8))
    assert all(r["method"] == "GET" for r in artifact["requests"])
    assert artifact["grant_role"] == "read"
    assert list(tmp_path.iterdir()) == [result]


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "not-composite"},
        {"id": SITE_ID.replace(HISTORICAL_SITE_GUID, str(UUID(int=6)))},
        {"id": SITE_ID.replace(HOST, "evil.example")},
        {"id": SITE_ID + "/items"},
        {"webUrl": SITE_URL + "/another"},
        {"webUrl": "https://evil.example/sites/EDNSystems"},
        {"webUrl": SITE_URL + "?items=true"},
    ],
)
def test_site_mismatch_stops_before_any_list(tmp_path, changes):
    values = responses()
    values[0].update(changes)
    transport = FakeTransport(values)
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path)
    assert len(transport.calls) == 1
    assert read_artifact(tmp_path)["site"] is None


@pytest.mark.parametrize("index", [1, 3, 5])
@pytest.mark.parametrize(
    "changes",
    [
        {"id": str(UUID(int=17))},
        {"displayName": "Different list"},
        {"webUrl": SITE_URL + "/Lists/../Other"},
        {"webUrl": SITE_URL + "/Lists/%2e%2e%2fOther"},
        {"webUrl": "https://evil.example/Lists/Projects"},
        {"list": {"template": "documentLibrary"}},
    ],
)
def test_every_list_verified_before_columns(tmp_path, index, changes):
    values = responses()
    values[index].update(changes)
    transport = FakeTransport(values)
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path)
    assert len(transport.calls) == index + 1
    assert transport.calls[-1].purpose.startswith("verify_")


@pytest.mark.parametrize(
    "url",
    [
        "https://graph.microsoft.com/v1.0/sites/x/lists/y/items",
        site_identity_request().url + "&$expand=items",
        site_identity_request().url + "&%24expand=items",
        site_identity_request().url.replace("graph.microsoft.com", "evil.example"),
        site_identity_request().url + "#ignored",
        "https://graph.microsoft.com/v1.0/drives",
        "https://graph.microsoft.com/v1.0/sites/x/permissions",
        "https://graph.microsoft.com/v1.0/sites/x/lists/y/attachments",
        "https://graph.microsoft.com/v1.0/sites/x/lists/y/versions",
        "https://graph.microsoft.com/v1.0/sites/x/drive/root/children",
    ],
)
def test_arbitrary_requests_denied_before_token_or_network(url):
    token = Mock(return_value="fake-token")
    transport = SchemaHttpTransport(token)
    with pytest.raises(SchemaInspectionError):
        transport.get(replace(site_identity_request(), url=url))
    token.assert_not_called()
    module.http.client.HTTPSConnection.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [{"method": "POST"}, {"maximum_records": 1000}, {"follow_continuation": True}],
)
def test_request_contract_cannot_be_relaxed(changes):
    with pytest.raises(SchemaInspectionError):
        validate_schema_request(replace(site_identity_request(), **changes))


@pytest.mark.parametrize("where", [0, 1, 2])
def test_pagination_never_followed(tmp_path, where):
    values = responses()
    values[where]["@odata.nextLink"] = "https://evil.example/SECRET"
    transport = FakeTransport(values)
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path)
    assert len(transport.calls) == where + 1
    assert "SECRET" not in (tmp_path / ARTIFACT_NAME).read_text()


@pytest.mark.parametrize("count,success", [(100, True), (101, False)])
def test_column_cap(tmp_path, count, success):
    values = responses()
    values[2] = {"value": [column(i + 1) for i in range(count)]}
    transport = FakeTransport(values)
    executor = SchemaExecutor(identity(), transport)
    if success:
        executor.run(tmp_path)
        assert len(read_artifact(tmp_path)["lists"][0]["columns"]) == 100
        assert len(transport.calls) == 7
    else:
        with pytest.raises(SchemaInspectionError):
            executor.run(tmp_path)
        assert len(transport.calls) == 3


@pytest.mark.parametrize(
    "reply",
    [
        SchemaReply(301, b"redirect"),
        SchemaReply(302, b"redirect"),
        SchemaReply(307, b"redirect"),
        SchemaReply(401, b"SECRET"),
        SchemaReply(403, b"SECRET"),
        SchemaReply(429, b"SECRET"),
        SchemaReply(500, b"SECRET"),
        SchemaReply(200, b"bad json SECRET"),
        SchemaReply(200, b'{"id":"one","id":"two"}'),
        SchemaReply(200, b"[]"),
        SchemaReply(200, b"x" * (MAX_BYTES + 1)),
        RuntimeError("Authorization: Bearer SECRET"),
    ],
)
def test_failure_consumes_attempt_no_retry_or_raw_error(tmp_path, reply):
    transport = FakeTransport([reply])
    executor = SchemaExecutor(identity(), transport)
    with pytest.raises(SchemaInspectionError, match="schema_inspection_failed"):
        executor.run(tmp_path)
    with pytest.raises(SchemaInspectionError):
        executor.run(tmp_path)
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path)
    assert len(transport.calls) == 1
    assert read_artifact(tmp_path)["state"] == "stopped"
    assert "SECRET" not in (tmp_path / ARTIFACT_NAME).read_text()


def test_success_not_replayed_on_same_instance_or_restart(tmp_path):
    transport = FakeTransport()
    executor = SchemaExecutor(identity(), transport)
    executor.run(tmp_path)
    before = (tmp_path / ARTIFACT_NAME).read_bytes()
    for again in [executor, SchemaExecutor(identity(), transport)]:
        with pytest.raises(SchemaInspectionError):
            again.run(tmp_path)
    assert len(transport.calls) == 7
    assert (tmp_path / ARTIFACT_NAME).read_bytes() == before


def test_allowlist_projection_no_raw_response_or_token_persistence(tmp_path):
    values = responses()
    for value in values:
        value["access_token"] = "SECRET"
        value["description"] = "PRIVATE_OPERATIONAL_TEXT"
        value["Authorization"] = "Bearer SECRET"
    values[2]["value"][0].update({"defaultValue": "PRIVATE_OPERATIONAL_TEXT"})
    values[2]["value"][0]["text"]["unexpected"] = "SECRET"
    transport = FakeTransport(values)
    SchemaExecutor(identity(), transport).run(tmp_path)
    output = (tmp_path / ARTIFACT_NAME).read_text()
    assert "SECRET" not in output and "PRIVATE_OPERATIONAL_TEXT" not in output
    assert "access_token" not in output and "Authorization" not in output


@pytest.mark.parametrize("key", ["items", "fields", "attachments", "versions"])
def test_operational_content_rejected_not_saved(tmp_path, key):
    values = responses()
    values[2][key] = [{"Title": "PRIVATE"}]
    transport = FakeTransport(values)
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path)
    assert len(transport.calls) == 3
    assert "PRIVATE" not in (tmp_path / ARTIFACT_NAME).read_text()


def test_lookup_preserved_without_target_traversal(tmp_path):
    values = responses()
    c = values[2]["value"][0]
    del c["text"]
    c["lookup"] = {
        "listId": str(UUID(int=28)),
        "columnName": "Title",
        "allowMultipleValues": False,
        "secret": "NOT_RETAINED",
    }
    transport = FakeTransport(values)
    SchemaExecutor(identity(), transport).run(tmp_path)
    output = read_artifact(tmp_path)
    assert output["lists"][0]["columns"][0]["lookup"]["listId"] == str(UUID(int=28))
    assert len(transport.calls) == 7
    assert all(str(UUID(int=28)) not in r.url for r in transport.calls)
    assert "NOT_RETAINED" not in json.dumps(output)


@pytest.mark.parametrize(
    "change",
    [
        {"text": None},
        {"required": "false"},
        {"choice": {"choices": ["x"]}},
        {"id": "bad"},
        {"name": None},
    ],
)
def test_malformed_column_fails_closed(tmp_path, change):
    values = responses()
    values[2]["value"][0].update(change)
    transport = FakeTransport(values)
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path)
    assert len(transport.calls) == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant", "wrong"),
        ("application", "wrong"),
        ("account", "wrong"),
        ("scopes", frozenset({"Sites.Read.All"})),
        ("scopes", frozenset({"Sites.Selected", "Sites.FullControl.All"})),
        ("grant_role", "write"),
        ("grant_id", ""),
    ],
)
def test_host_identity_gate(field, value):
    with pytest.raises(SchemaInspectionError):
        replace(identity(), **{field: value})


def http_mock(monkeypatch, *, status=200, headers=None, body=b"{}"):
    response = Mock()
    response.status = status
    all_headers = {"Content-Type": "application/json", **(headers or {})}
    response.getheader.side_effect = lambda k, default=None: all_headers.get(k, default)
    response.read.return_value = body
    connection = Mock()
    connection.getresponse.return_value = response
    factory = Mock(return_value=connection)
    monkeypatch.setattr(module.http.client, "HTTPSConnection", factory)
    return connection, factory


@pytest.mark.parametrize(
    "status,headers",
    [
        (301, {}),
        (302, {}),
        (307, {}),
        (308, {}),
        (429, {}),
        (200, {"Location": "https://evil.example"}),
        (200, {"Content-Type": "text/html"}),
        (200, {"Content-Encoding": "gzip"}),
    ],
)
def test_real_transport_never_redirects_or_retries(monkeypatch, status, headers):
    connection, factory = http_mock(monkeypatch, status=status, headers=headers)
    transport = SchemaHttpTransport(lambda: "FAKE_SECRET")
    for _ in range(2):
        with pytest.raises(SchemaInspectionError):
            transport.get(site_identity_request())
    assert connection.request.call_count == 1
    assert factory.call_count == 1
    connection.close.assert_called_once()


def test_transport_is_fixed_host_get_and_blocks_duplicate(monkeypatch):
    connection, factory = http_mock(
        monkeypatch, body=json.dumps(responses()[0]).encode()
    )
    transport = SchemaHttpTransport(lambda: "FAKE_SECRET")
    transport.get(site_identity_request())
    factory.assert_called_once_with("graph.microsoft.com", timeout=30)
    assert connection.request.call_args.args[0] == "GET"
    with pytest.raises(SchemaInspectionError):
        transport.get(site_identity_request())
    assert connection.request.call_count == 1


def test_transport_itself_enforces_order_and_site_before_list(monkeypatch):
    connection, _ = http_mock(monkeypatch)
    token = Mock(return_value="FAKE_SECRET")
    transport = SchemaHttpTransport(token)
    request = list_schema_requests(resolved_site_id=SITE_ID, resolved_web_url=SITE_URL)[
        0
    ]
    with pytest.raises(SchemaInspectionError):
        transport.get(request)
    connection.request.assert_not_called()
    token.assert_not_called()


def test_http_boundary_full_sequence_and_eighth_request_denied(tmp_path, monkeypatch):
    connection, factory = http_mock(monkeypatch)
    response = connection.getresponse.return_value
    response.read.side_effect = [json.dumps(v).encode() for v in responses()]
    transport = SchemaHttpTransport(lambda: "FAKE_SECRET_NEVER_SAVED")
    SchemaExecutor(identity(), transport).run(tmp_path)
    assert connection.request.call_count == factory.call_count == 7
    with pytest.raises(SchemaInspectionError):
        transport.get(site_identity_request())
    assert connection.request.call_count == 7
    assert "FAKE_SECRET_NEVER_SAVED" not in (tmp_path / ARTIFACT_NAME).read_text()


def test_transport_stops_before_columns_on_invalid_list_response(monkeypatch):
    connection, _ = http_mock(monkeypatch)
    values = responses()
    values[1]["id"] = "wrong"
    connection.getresponse.return_value.read.side_effect = [
        json.dumps(v).encode() for v in values[:2]
    ]
    transport = SchemaHttpTransport(lambda: "FAKE_SECRET")
    plan = list_schema_requests(resolved_site_id=SITE_ID, resolved_web_url=SITE_URL)
    transport.get(site_identity_request())
    with pytest.raises(SchemaInspectionError):
        transport.get(plan[0])
    with pytest.raises(SchemaInspectionError):
        transport.get(plan[1])
    assert connection.request.call_count == 2


@pytest.mark.parametrize(
    "kind", ["empty", "duplicate", "missing", "nan", "nested_next"]
)
def test_additional_schema_fail_closed_cases(tmp_path, kind):
    values = responses()
    if kind == "empty":
        values[2]["value"] = []
    elif kind == "duplicate":
        values[2]["value"] *= 2
    elif kind == "missing":
        del values[2]["value"][0]["hidden"]
    elif kind == "nan":
        c = values[2]["value"][0]
        del c["text"]
        c["number"] = {"minimum": float("nan")}
    else:
        values[2]["extension"] = {"@odata.nextLink": "https://evil.example"}
    transport = FakeTransport(values)
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path)
    assert len(transport.calls) == 3


def test_no_calls_if_storage_missing_or_preexisting_marker(tmp_path):
    transport = FakeTransport()
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path / "missing")
    (tmp_path / ARTIFACT_NAME).write_text("interrupted prior attempt")
    with pytest.raises(SchemaInspectionError):
        SchemaExecutor(identity(), transport).run(tmp_path)
    assert transport.calls == []
    assert (tmp_path / ARTIFACT_NAME).read_text() == "interrupted prior attempt"


def test_audit_records_attempt_before_transport_and_seven_day_retention(tmp_path):
    from datetime import datetime, timedelta

    class AuditAware(FakeTransport):
        def get(self, request):
            before = read_artifact(tmp_path)
            assert before["requests"][-1]["state"] == "attempted"
            assert len(before["requests"]) == len(self.calls) + 1
            return super().get(request)

    SchemaExecutor(identity(), AuditAware()).run(tmp_path)
    audit = read_artifact(tmp_path)
    assert datetime.fromisoformat(audit["delete_by"]) - datetime.fromisoformat(
        audit["started_at"]
    ) == timedelta(days=7)
    assert all(r["state"] == "verified" for r in audit["requests"])
