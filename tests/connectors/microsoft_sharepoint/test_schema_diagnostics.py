"""Synthetic HTTP diagnostics through the real bounded executor and transport."""

import json
from unittest.mock import Mock

import pytest
from test_schema_executor import column, identity, responses

from edn.connectors.microsoft_sharepoint import schema_executor as m


@pytest.mark.parametrize(
    "status,body,headers,reason,category",
    [
        (
            403,
            {"error": {"code": "accessDenied", "message": "SECRET"}},
            {},
            "http_authorization",
            "authentication_authorization",
        ),
        (
            400,
            {"error": {"code": "invalidRequest", "message": "SECRET"}},
            {},
            "graph_error",
            "graph_error",
        ),
        (200, b"{SECRET", {}, "malformed_json", "malformed_json"),
        (
            200,
            {"value": [dict(column(), text=None, geolocation={"secret": "SECRET"})]},
            {},
            "column_type_facet_unsupported",
            "unsupported_schema_facet",
        ),
        (
            200,
            {"value": [column()], "@odata.nextLink": "https://SECRET"},
            {},
            "continuation_prohibited",
            "pagination",
        ),
        (302, {}, {"Location": "https://SECRET"}, "redirect_prohibited", "redirect"),
        (
            200,
            {"value": [], "items": ["SECRET"]},
            {},
            "operational_content",
            "prohibited_content",
        ),
        (
            200,
            {"value": None},
            {},
            "columns_value_not_array",
            "unexpected_response_shape",
        ),
        (
            200,
            {"value": [{"id": "SECRET"}]},
            {},
            "column_required_field_missing",
            "projection_field_incompatibility",
        ),
        (
            400,
            {"error": {"code": "SECRET", "message": "SECRET"}},
            {},
            "graph_error",
            "graph_error",
        ),
    ],
)
def test_failed_third_request_audit(
    tmp_path, monkeypatch, status, body, headers, reason, category
):
    values = responses()
    response_values = []
    for index in range(3):
        response = Mock()
        response.status = status if index == 2 else 200
        response_headers = {
            "Content-Type": "application/json",
            "request-id": "12345678-1234-1234-1234-123456789abc",
            "client-request-id": "SECRET",
            "Set-Cookie": "SECRET",
            **(headers if index == 2 else {}),
        }
        response.getheader.side_effect = lambda k, default=None, h=response_headers: (
            h.get(k, default)
        )
        value = body if index == 2 else values[index]
        response.read.return_value = (
            value if isinstance(value, bytes) else json.dumps(value).encode()
        )
        response_values.append(response)
    connection = Mock()
    connection.getresponse.side_effect = response_values
    factory = Mock(return_value=connection)
    monkeypatch.setattr(m.http.client, "HTTPSConnection", factory)
    with pytest.raises(m.SchemaInspectionError):
        m.SchemaExecutor(identity(), m.SchemaHttpTransport(lambda: "TOKEN_SECRET")).run(
            tmp_path
        )
    assert connection.request.call_count == 3
    text = (tmp_path / m.ARTIFACT_NAME).read_text()
    assert (
        "SECRET" not in text
        and "Authorization" not in text
        and "Set-Cookie" not in text
    )
    audit = json.loads(text)
    info = audit["requests"][-1]["diagnostic"]
    assert info["http_status"] == status
    assert info["failure_reason"] == reason
    assert info["failure_category"] == category
    assert info["network_dispatch_completed"] and info["response_received"]
    assert info["request_id"] == "12345678-1234-1234-1234-123456789abc"
    assert info["client_request_id"] is None
    assert info["pagination_rejected"] == (category == "pagination")
    assert info["redirect_rejected"] == (category == "redirect")
    assert audit["requests"][-1]["endpoint_class"] == "list_columns"
    assert "url" not in audit["requests"][-1]


def test_transport_failure_is_sanitized(tmp_path, monkeypatch):
    connection = Mock()
    connection.request.side_effect = OSError("SECRET")
    monkeypatch.setattr(m.http.client, "HTTPSConnection", Mock(return_value=connection))
    with pytest.raises(m.SchemaInspectionError):
        m.SchemaExecutor(identity(), m.SchemaHttpTransport(lambda: "TOKEN_SECRET")).run(
            tmp_path
        )
    text = (tmp_path / m.ARTIFACT_NAME).read_text()
    info = json.loads(text)["requests"][0]["diagnostic"]
    assert info["failure_category"] == "transport"
    assert info["network_dispatch_started"] and not info["network_dispatch_completed"]
    assert not info["response_received"] and info["http_status"] is None
    assert "SECRET" not in text


def test_unknown_properties_discarded_and_partial_validation_count(tmp_path):
    from test_schema_executor import FakeTransport

    values = responses()
    values[2]["value"] = [
        dict(column(), description="SECRET"),
        dict(column(2), text=[]),
    ]
    with pytest.raises(m.SchemaInspectionError):
        m.SchemaExecutor(identity(), FakeTransport(values)).run(tmp_path)
    text = (tmp_path / m.ARTIFACT_NAME).read_text()
    assert "SECRET" not in text
    assert json.loads(text)["requests"][-1]["diagnostic"]["validated_records"] == 1


def test_audit_write_failure_prevents_dispatch(tmp_path, monkeypatch):
    transport = Mock()
    monkeypatch.setattr(m.os, "fsync", Mock(side_effect=OSError("SECRET")))
    with pytest.raises(m.SchemaInspectionError, match=r"^audit_write_failed$"):
        m.SchemaExecutor(identity(), transport).run(tmp_path)
    transport.get.assert_not_called()


@pytest.mark.parametrize(
    "exc,reason",
    [
        (RuntimeError("SECRET"), "internal_failure"),
        (m.SchemaInspectionError("SECRET"), "internal_failure"),
        (m.SchemaInspectionError("list_identity_mismatch"), "list_identity_mismatch"),
        (m.SchemaInspectionError("audit_write_failed"), "audit_write_failed"),
    ],
)
def test_reason_allowlist(exc, reason):
    info = m.diagnostic()
    m.record_failure(info, exc)
    assert info["failure_reason"] == reason
    assert "SECRET" not in json.dumps(info)
