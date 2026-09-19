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
    "scope", ["", "Sites.Read.All", "Sites.Selected Mail.Read", "Sites.FullControl.All"]
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
