import pytest

from edn.operations.cli import main, runtime_database
from edn.operations.storage import EventStore


def test_explicit_init_under_data_root(tmp_path, capsys):
    path = tmp_path / "events.db"
    assert main(["init", "--database", str(path), "--data-root", str(tmp_path)]) == 0
    assert path.exists()
    assert '"initialized": true' in capsys.readouterr().out


def test_path_escape_and_repository_data_rejected(tmp_path):
    with pytest.raises(ValueError):
        runtime_database(str(tmp_path / "events.db"), str(tmp_path / "other"))
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        runtime_database(str(tmp_path / "events.db"), str(tmp_path))


def test_delegated_import_checks_account_and_replays(tmp_path, monkeypatch, capsys):
    from edn.operations import cli

    path = tmp_path / "events.db"
    store = EventStore(path)
    store.initialise()
    monkeypatch.setenv("EDN_OPERATIONS_MAILBOXES", "edn@example.com")
    monkeypatch.setenv("EDN_MS_TENANT_ID", "synthetic-tenant")
    monkeypatch.setenv("EDN_MS_CLIENT_ID", "synthetic-client")

    class Credential:
        def __init__(self, tenant, client, scopes):
            assert scopes == ("User.Read", "Mail.Read")

    class Client:
        def __init__(self, credential, mailboxes):
            pass

        def account(self):
            return {"mail": "edn@example.com"}

        def page(self, *args, **kwargs):
            return {
                "value": [
                    {
                        "id": "m1",
                        "receivedDateTime": "2026-10-01T12:00:00Z",
                        "body": {"contentType": "text", "content": "Source"},
                    }
                ]
            }

    monkeypatch.setattr(cli, "DeviceCodeCredential", Credential)
    monkeypatch.setattr(cli, "OperationsOutlookClient", Client)
    arguments = [
        "ingest-outlook",
        "--database",
        str(path),
        "--data-root",
        str(tmp_path),
        "--start",
        "2026-10-01T00:00:00Z",
        "--end",
        "2026-10-02T00:00:00Z",
    ]
    assert main(arguments) == 0
    assert main(arguments) == 0
    output = capsys.readouterr().out
    assert '"inserted": 1' in output and '"duplicates": 1' in output
    assert len(store.list_events()) == 1
    monkeypatch.setenv("EDN_OPERATIONS_MAILBOXES", "personal@example.com")
    with pytest.raises(SystemExit):
        main(arguments)
    assert len(store.list_events()) == 1


def test_application_import_multiple_mailboxes(tmp_path, monkeypatch, capsys):
    from edn.operations import cli

    path = tmp_path / "events.db"
    store = EventStore(path)
    store.initialise()
    accounts = ("owner@business.example", "operations@business.example")
    monkeypatch.setenv("EDN_OPERATIONS_MAILBOXES", ",".join(accounts))
    monkeypatch.setenv("EDN_MS_TENANT_ID", "synthetic-tenant")
    monkeypatch.setenv("EDN_MS_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("EDN_MS_CLIENT_SECRET", "synthetic-secret")

    class Credential:
        def __init__(self, tenant, client, secret):
            assert (tenant, client, secret) == (
                "synthetic-tenant",
                "synthetic-client",
                "synthetic-secret",
            )

    class Client:
        def __init__(self, credential, mailboxes):
            assert mailboxes == accounts

        def page(self, *args, **kwargs):
            return {
                "value": [{"id": "same-id", "receivedDateTime": "2026-10-01T12:00:00Z"}]
            }

    monkeypatch.setattr(cli, "ApplicationCredential", Credential)
    monkeypatch.setattr(cli, "OperationsOutlookClient", Client)
    assert (
        main(
            [
                "ingest-outlook",
                "--auth",
                "application",
                "--database",
                str(path),
                "--data-root",
                str(tmp_path),
                "--start",
                "2026-10-01T00:00:00Z",
                "--end",
                "2026-10-02T00:00:00Z",
            ]
        )
        == 0
    )
    assert {event.source_account for event in store.list_events()} == set(accounts)
    assert "synthetic-secret" not in capsys.readouterr().out
