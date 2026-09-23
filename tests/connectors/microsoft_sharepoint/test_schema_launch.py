"""Synthetic launch tests: authentication and network are always replaced."""

from unittest.mock import Mock

import pytest

from edn.connectors.microsoft_sharepoint import schema_launch as module
from edn.connectors.microsoft_sharepoint.schema_executor import SchemaInspectionError


def auth():
    return {
        "access_token": "SYNTHETIC",
        "scope": "Sites.Selected",
        "id_token_claims": {
            "tid": module.TENANT,
            "aud": module.APPLICATION,
            "preferred_username": module.ACCOUNT,
        },
    }


def acl():
    admin = "S-1-5-21-2158520141-276418557-3228345628-1001"
    return {
        "execution_sid": module.EXECUTION_SID,
        "owner_sid": module.PREPARATION_SID,
        "admin_sid": admin,
        "protected": True,
        "rules": [
            {
                "sid": sid,
                "rights": rights,
                "type": "Allow",
                "inherited": False,
                "inheritance": 3,
                "propagation": 0,
            }
            for sid, rights in [
                ("S-1-5-18", 2032127),
                ("S-1-5-32-544", 2032127),
                (admin, 2032127),
                (module.EXECUTION_SID, 1245631),
            ]
        ],
    }


def test_exact_acl():
    module.validate_acl(acl())


def test_offline_preparation_cannot_authorize_network_execution():
    evidence = acl()
    evidence["execution_sid"] = module.PREPARATION_SID
    with pytest.raises(SchemaInspectionError):
        module.validate_acl(evidence)
    evidence["execution_sid"] = module.EXECUTION_SID
    module.validate_acl(evidence)


def test_offline_access_entry_is_not_retained():
    evidence = acl()
    evidence["rules"][-1]["sid"] = module.PREPARATION_SID
    with pytest.raises(SchemaInspectionError):
        module.validate_acl(evidence)


def test_storage_transition_failure_after_auth_blocks_transport(monkeypatch):
    monkeypatch.setattr(
        module,
        "check_storage",
        Mock(side_effect=[None, SchemaInspectionError("identity_transition")]),
    )
    app = Mock()
    app.acquire_token_interactive.return_value = auth()
    monkeypatch.setattr(module.msal, "PublicClientApplication", Mock(return_value=app))
    transport = Mock()
    monkeypatch.setattr(module, "SchemaHttpTransport", transport)
    with pytest.raises(SchemaInspectionError):
        module.launch()
    transport.assert_not_called()


@pytest.mark.parametrize(
    "case", ["broad", "inherited", "unprotected", "identity", "rights", "owner"]
)
def test_acl_fails_closed(case):
    value = acl()
    if case == "broad":
        value["rules"][0]["sid"] = "S-1-5-32-545"
    elif case == "inherited":
        value["rules"][0]["inherited"] = True
    elif case == "unprotected":
        value["protected"] = False
    elif case == "identity":
        value["execution_sid"] = "other"
    elif case == "owner":
        value["owner_sid"] = "other"
    else:
        value["rules"][-1]["rights"] = 2032127
    with pytest.raises(SchemaInspectionError):
        module.validate_acl(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tid", "other"),
        ("aud", "other"),
        ("preferred_username", "admin@ednsystems.com.au"),
    ],
)
def test_wrong_auth_identity(field, value):
    result = auth()
    result["id_token_claims"][field] = value
    with pytest.raises(SchemaInspectionError):
        module.validate_auth(result)


@pytest.mark.parametrize(
    "scope",
    ["", "Sites.Read.All", "Sites.Selected Sites.Read.All", "Sites.FullControl.All"],
)
def test_wrong_auth_scopes(scope):
    result = auth()
    result["scope"] = scope
    with pytest.raises(SchemaInspectionError):
        module.validate_auth(result)


def test_launch_storage_precedes_auth_and_fixed_executor(monkeypatch):
    order = []
    monkeypatch.setattr(module, "check_storage", lambda: order.append("storage"))
    result = auth()
    app = Mock()
    app.acquire_token_interactive.side_effect = lambda **kw: (
        order.append("auth") or result
    )
    factory = Mock(return_value=app)
    monkeypatch.setattr(module.msal, "PublicClientApplication", factory)
    transport = Mock()

    def make_transport(supplier):
        assert supplier() == "SYNTHETIC"
        order.append("transport")
        return transport

    monkeypatch.setattr(module, "SchemaHttpTransport", make_transport)
    executor = Mock()
    monkeypatch.setattr(module, "SchemaExecutor", executor)
    module.launch()
    assert order == ["storage", "auth", "storage", "transport"]
    assert result == {}
    assert factory.call_args.args == (module.APPLICATION,)
    assert app.acquire_token_interactive.call_args.kwargs["scopes"] == list(
        module.SCOPES
    )
    executor.return_value.run.assert_called_once_with(module.OUTPUT)
    assert executor.call_args.args[0].grant_id == module.GRANT_ID


def test_storage_failure_never_authenticates(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(module.msal, "PublicClientApplication", factory)
    monkeypatch.setattr(
        module, "check_storage", Mock(side_effect=SchemaInspectionError("storage"))
    )
    with pytest.raises(SchemaInspectionError):
        module.launch()
    factory.assert_not_called()


def test_auth_failure_never_constructs_transport(monkeypatch):
    monkeypatch.setattr(module, "check_storage", lambda: None)
    app = Mock()
    app.acquire_token_interactive.return_value = {"error": "synthetic"}
    monkeypatch.setattr(module.msal, "PublicClientApplication", Mock(return_value=app))
    transport = Mock()
    monkeypatch.setattr(module, "SchemaHttpTransport", transport)
    with pytest.raises(SchemaInspectionError):
        module.launch()
    transport.assert_not_called()


@pytest.mark.parametrize(
    "failure", [TimeoutError("SECRET"), KeyboardInterrupt(), RuntimeError("SECRET")]
)
def test_discovery_failure_is_sanitized_and_blocks_graph(monkeypatch, capsys, failure):
    monkeypatch.setattr(module, "check_storage", lambda: None)
    monkeypatch.setattr(
        module.msal, "PublicClientApplication", Mock(side_effect=failure)
    )
    transport = Mock()
    monkeypatch.setattr(module, "SchemaHttpTransport", transport)
    with pytest.raises(SchemaInspectionError):
        module.launch()
    transport.assert_not_called()
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err
    assert "AUTH: preparing" in output.out


@pytest.mark.parametrize("accepted", [True, False])
def test_browser_handoff_and_safe_manual_link(monkeypatch, capsys, accepted):
    browser = Mock(return_value=accepted)
    monkeypatch.setattr(module.webbrowser, "open", browser)
    with module.browser_delivery() as status:
        assert module.webbrowser.open(module.LANDING_URL) is accepted
        assert status["failed"] is not accepted
    assert module.webbrowser.open is browser
    output = capsys.readouterr().out
    assert ("handoff accepted" if accepted else "handoff failed") in output
    assert "auth_uri" not in output


def test_callback_timeout_and_secrets_never_logged(monkeypatch, capsys):
    import logging

    from msal.oauth2cli.oauth2 import BrowserInteractionTimeoutError

    monkeypatch.setattr(module, "check_storage", lambda: None)
    app = Mock()

    def wait(**kwargs):
        logging.getLogger("msal").warning("SECRET token code state pkce cookie")
        assert kwargs["timeout"] == 600
        assert "$auth_uri" in kwargs["welcome_template"]
        assert "$" not in kwargs["error_template"]
        raise BrowserInteractionTimeoutError("SECRET")

    app.acquire_token_interactive.side_effect = wait
    factory = Mock(return_value=app)
    monkeypatch.setattr(module.msal, "PublicClientApplication", factory)
    transport = Mock()
    monkeypatch.setattr(module, "SchemaHttpTransport", transport)
    with pytest.raises(SchemaInspectionError):
        module.launch()
    assert factory.call_args.kwargs["timeout"] == 20
    assert factory.call_args.kwargs["exclude_scopes"] == ["offline_access"]
    transport.assert_not_called()
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err
    assert "browser callback timeout" in output.out


def test_failed_handoff_even_with_synthetic_result_cannot_execute(monkeypatch):
    monkeypatch.setattr(module, "check_storage", lambda: None)
    monkeypatch.setattr(module.webbrowser, "open", Mock(side_effect=OSError("SECRET")))
    app = Mock()

    def interaction(**kwargs):
        module.webbrowser.open(module.LANDING_URL)
        return auth()

    app.acquire_token_interactive.side_effect = interaction
    monkeypatch.setattr(module.msal, "PublicClientApplication", Mock(return_value=app))
    transport = Mock()
    monkeypatch.setattr(module, "SchemaHttpTransport", transport)
    with pytest.raises(SchemaInspectionError):
        module.launch()
    transport.assert_not_called()


@pytest.mark.parametrize(
    "location,key,value,reason",
    [
        ("claims", "tid", "SECRET", "tenant_mismatch"),
        ("claims", "aud", "SECRET", "client_id_mismatch"),
        ("claims", "preferred_username", "admin@ednsystems.com.au", "account_mismatch"),
        ("claims", "tid", None, "claims_missing"),
        ("result", "id_token_claims", None, "claims_missing"),
        ("result", "scope", "Mail.Read Calendars.Read", "required_scope_missing"),
        ("result", "scope", "Sites.Selected Sites.Read.All", "unexpected_scope"),
        ("result", "scope", [], "scope_format"),
        ("result", "access_token", "SECRET\n", "token_invalid"),
        ("result", "error", "consent_required", "consent_required"),
        ("result", "error", "SECRET", "response_error"),
    ],
)
def test_validation_reason_blocks_graph_and_never_leaks(
    monkeypatch, capsys, caplog, tmp_path, location, key, value, reason
):
    result = auth()
    result.update(
        {
            "refresh_token": "SECRET",
            "id_token": "SECRET",
            "error_description": "SECRET",
            "code": "SECRET",
            "cookie": "SECRET",
        }
    )
    target = result["id_token_claims"] if location == "claims" else result
    target[key] = value
    with pytest.raises(SchemaInspectionError, match="^authentication_" + reason + "$"):
        module.validate_auth(result)
    monkeypatch.setattr(module, "check_storage", lambda: None)
    monkeypatch.setattr(module, "OUTPUT", tmp_path)
    app = Mock()
    app.acquire_token_interactive.return_value = result
    monkeypatch.setattr(module.msal, "PublicClientApplication", Mock(return_value=app))
    transport, executor = Mock(), Mock()
    monkeypatch.setattr(module, "SchemaHttpTransport", transport)
    monkeypatch.setattr(module, "SchemaExecutor", executor)
    with pytest.raises(SchemaInspectionError):
        module.launch()
    transport.assert_not_called()
    executor.assert_not_called()
    output = capsys.readouterr()
    assert "reason=authentication_" + reason + ";" in output.out
    assert "SECRET" not in output.out + output.err + caplog.text
    assert result == {}
    assert list(tmp_path.iterdir()) == []


def test_invalid_result_has_safe_reason():
    with pytest.raises(SchemaInspectionError, match="authentication_result_invalid"):
        module.validate_auth(None)


@pytest.mark.parametrize(
    "scope",
    [
        "Sites.Selected",
        "Sites.Selected User.Read",
        "Sites.Selected Mail.Read",
        "Sites.Selected Calendars.Read",
        "Sites.Selected User.Read Mail.Read Calendars.Read",
        "https://graph.microsoft.com/Sites.Selected openid profile",
        "Sites.Selected https://graph.microsoft.com/Mail.Read",
    ],
)
def test_expected_identity_and_scopes_pass(scope):
    result = auth()
    result["scope"] = scope
    result["id_token_claims"]["preferred_username"] = module.ACCOUNT.upper()
    assert module.validate_auth(result) == "SYNTHETIC"


def test_untrusted_exception_text_is_not_a_reason(monkeypatch, capsys):
    app = Mock()
    app.acquire_token_interactive.return_value = auth()
    monkeypatch.setattr(module.msal, "PublicClientApplication", Mock(return_value=app))
    monkeypatch.setattr(
        module, "validate_auth", Mock(side_effect=SchemaInspectionError("SECRET"))
    )
    with pytest.raises(SchemaInspectionError):
        module.authenticate()
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err
    assert "reason=authentication_delivery_failed" in output.out


@pytest.mark.parametrize(
    "scope",
    [
        "Sites.Selected Sites.Read.All Sites.FullControl.All Sites.Read.All",
        "https://graph.microsoft.com/Sites.Read.All "
        "Sites.Selected Sites.FullControl.All",
    ],
)
def test_scope_names_sorted_deduplicated_and_expected_excluded(capsys, scope):
    import json

    result = auth()
    result["scope"] = scope
    with pytest.raises(SchemaInspectionError, match="authentication_unexpected_scope"):
        module.validate_auth(result)
    report = json.loads(capsys.readouterr().out.split("scope_diagnostic=", 1)[1])
    assert report == {
        "expected": ["Sites.Selected"],
        "allowed": sorted(module.ALLOWED_APPLICATION_SCOPES),
        "unexpected": ["Sites.FullControl.All", "Sites.Read.All"],
        "unrecognized_redacted": False,
    }


def test_scope_diagnostic_redacts_arbitrary_material_and_preserves_casing(capsys):
    result = auth()
    result["scope"] = "Sites.Selected user.read SECRET eyJ.fake.signature"
    result["access_token"] = "TOKEN_SECRET"
    result["refresh_token"] = "REFRESH_SECRET"
    with pytest.raises(SchemaInspectionError, match="authentication_unexpected_scope"):
        module.validate_auth(result)
    output = capsys.readouterr().out
    assert '"unexpected": []' in output
    assert '"unrecognized_redacted": true' in output
    assert "SECRET" not in output
    assert "eyJ" not in output
    assert "user.read" not in output
    result["scope"] = "sites.selected"
    with pytest.raises(
        SchemaInspectionError, match="authentication_required_scope_missing"
    ):
        module.validate_auth(result)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "scope",
    [
        "Sites.Selected Unknown.Read",
        "Sites.Selected mail.read",
        "Sites.Selected Mail.ReadWrite",
        "Sites.Selected Mail.Read/",
        "Sites.Selected https://GRAPH.microsoft.com/Mail.Read",
    ],
)
def test_unapproved_or_similar_scopes_fail(scope):
    result = auth()
    result["scope"] = scope
    with pytest.raises(SchemaInspectionError, match="authentication_unexpected_scope"):
        module.validate_auth(result)


def test_shared_scopes_do_not_expand_operation_authority(monkeypatch):
    monkeypatch.setattr(module, "check_storage", lambda: None)
    result = auth()
    result["scope"] = "Sites.Selected User.Read Mail.Read Calendars.Read"
    app = Mock()
    app.acquire_token_interactive.return_value = result
    monkeypatch.setattr(module.msal, "PublicClientApplication", Mock(return_value=app))
    monkeypatch.setattr(module, "SchemaHttpTransport", Mock())
    executor = Mock()
    monkeypatch.setattr(module, "SchemaExecutor", executor)
    module.launch()
    assert executor.call_args.args[0].scopes == frozenset({"Sites.Selected"})
    assert app.acquire_token_interactive.call_args.kwargs["scopes"] == list(
        module.SCOPES
    )


@pytest.mark.parametrize(
    "path",
    [
        "/me/messages",
        "/me/calendar/events",
        "/users",
        "/me/drive",
        "/sites/example/permissions",
        "/sites/example/lists/example/items",
    ],
)
def test_shared_token_cannot_reach_other_endpoints(monkeypatch, path):
    from dataclasses import replace

    from edn.connectors.microsoft_sharepoint import schema_executor as executor
    from edn.connectors.microsoft_sharepoint.schema_plan import site_identity_request

    network = Mock()
    monkeypatch.setattr(executor.http.client, "HTTPSConnection", network)
    supplier = Mock(return_value="SYNTHETIC")
    transport = executor.SchemaHttpTransport(supplier)
    request = replace(
        site_identity_request(), url="https://graph.microsoft.com/v1.0" + path
    )
    with pytest.raises(SchemaInspectionError, match="request_not_allowlisted"):
        executor.validate_schema_request(request)
    with pytest.raises(SchemaInspectionError, match="transport_failed"):
        transport.get(request)
    supplier.assert_not_called()
    network.assert_not_called()
