"""Durable synthetic transport receipts. This module never calls Microsoft."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from edn.operations.intake_security import AnchoredDirectory, require_supported_platform


class SyntheticSyncError(ValueError):
    """Synthetic delivery is unconfirmed or its receipt is invalid."""


def delivery_identity(payload: dict[str, Any]) -> dict[str, Any]:
    """Bind an attempt to an approved exact snapshot and stable delivery key."""
    try:
        request_id = payload["request_id"]
        revision = payload["revision"]
        content_hash = payload["content_hash"]
        key = payload["idempotency_key"]
        approval = payload["approval"]
        if (
            not isinstance(request_id, str)
            or str(UUID(request_id)) != request_id
            or type(revision) is not int
            or revision < 1
            or not isinstance(content_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", content_hash) is None
            or not isinstance(key, str)
            or not 1 <= len(key) <= 256
            or any(ord(char) < 33 or ord(char) > 126 for char in key)
            or not isinstance(approval, dict)
            or type(approval.get("revision")) is not int
            or approval.get("revision") != revision
            or approval.get("content_hash") != content_hash
            or payload.get("dry_run") is not True
            or payload.get("not_synced") is not True
            or payload.get("sync_status") != "dry_run"
            or not isinstance(payload.get("fields"), dict)
        ):
            raise ValueError
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        if len(encoded) > 65536:
            raise ValueError
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        UnicodeError,
        RecursionError,
    ):
        raise SyntheticSyncError(
            "Approved synthetic delivery snapshot is invalid"
        ) from None
    return {
        "request_id": request_id,
        "revision": revision,
        "content_hash": content_hash,
        "idempotency_key": key,
        "payload_hash": hashlib.sha256(encoded).hexdigest(),
    }


class SyntheticSyncStore:
    """Private local ledger models failures and ambiguous acknowledgements."""

    def __init__(self, root: Path):
        require_supported_platform()
        self.root = Path(root)
        with AnchoredDirectory(self.root):
            pass

    @staticmethod
    def _read(anchor: AnchoredDirectory, name: str) -> dict[str, Any] | None:
        if not anchor.exists(name):
            return None
        descriptor = anchor.open_file(name)
        try:
            with os.fdopen(descriptor, "rb") as incoming:
                raw = incoming.read(65537)
            if len(raw) > 65536:
                raise ValueError
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, UnicodeError, RecursionError):
            raise SyntheticSyncError("Stored synthetic receipt is invalid") from None

    @staticmethod
    def _write(anchor: AnchoredDirectory, name: str, value: dict[str, Any]) -> None:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        if len(raw) > 65536:
            raise SyntheticSyncError("Synthetic receipt exceeds its bound")
        pending = ".pending-" + str(uuid4())
        descriptor = anchor.open_file(pending, create=True, write=True)
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        # Existing receipts were verified while holding the same private lock.
        if anchor.exists(name):
            checked = anchor.open_file(name)
            os.close(checked)
            anchor.replace(pending, name)
        else:
            anchor.publish(pending, name)
        # A fault here leaves an uncertain commit; callers must reload/reconcile.
        os.fsync(anchor.fd)

    @staticmethod
    def _name(identity: dict[str, Any], suffix: str) -> str:
        key = hashlib.sha256(identity["idempotency_key"].encode()).hexdigest()
        return key + suffix

    def get(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        identity = delivery_identity(payload)
        with AnchoredDirectory(self.root) as anchor, anchor.lock("sync.lock"):
            receipt = self._read(anchor, self._name(identity, ".receipt.json"))
            if receipt is not None:
                self._validate(receipt, identity)
                self._confirmed(anchor, receipt, identity)
            return receipt

    @staticmethod
    def _validate(receipt: dict[str, Any], identity: dict[str, Any]) -> None:
        SyntheticSyncStore._stored_identity(receipt.get("identity"), identity)
        if (
            set(receipt)
            != {
                "identity",
                "status",
                "mode",
                "live_synced",
                "attempt",
                "actor",
                "timestamp",
                "synthetic_id",
            }
            or receipt.get("mode") != "synthetic"
            or receipt.get("live_synced") is not False
            or not isinstance(receipt.get("status"), str)
            or receipt.get("status") not in {"pending", "failed", "unknown", "synced"}
            or type(receipt.get("attempt")) is not int
            or receipt["attempt"] < 1
        ):
            raise SyntheticSyncError(
                "Synthetic receipt does not match this approved version"
            )
        try:
            timestamp = datetime.fromisoformat(receipt["timestamp"])
            if timestamp.utcoffset() != UTC.utcoffset(timestamp):
                raise ValueError
            if (
                re.fullmatch(r"local operator, uid=(0|[1-9][0-9]*)", receipt["actor"])
                is None
            ):
                raise ValueError
            identifier = receipt["synthetic_id"]
            if receipt["status"] == "synced":
                SyntheticSyncStore._synthetic_id(identifier)
            elif identifier is not None:
                raise ValueError
        except (KeyError, ValueError, TypeError, AttributeError):
            raise SyntheticSyncError("Stored synthetic receipt is invalid") from None

    @staticmethod
    def _stored_identity(value: Any, expected: dict[str, Any]) -> None:
        if (
            not isinstance(value, dict)
            or set(value) != set(expected)
            or type(value.get("revision")) is not int
            or any(
                not isinstance(value.get(key), str)
                for key in expected
                if key != "revision"
            )
            or value != expected
        ):
            raise SyntheticSyncError(
                "Stored synthetic identity does not match approved content"
            )

    @staticmethod
    def _ledger(value: dict[str, Any], identity: dict[str, Any]) -> None:
        if set(value) != {"identity", "synthetic_id"}:
            raise SyntheticSyncError("Stored synthetic ledger is invalid")
        SyntheticSyncStore._stored_identity(value.get("identity"), identity)
        SyntheticSyncStore._synthetic_id(value.get("synthetic_id"))

    def _confirmed(
        self,
        anchor: AnchoredDirectory,
        receipt: dict[str, Any],
        identity: dict[str, Any],
    ) -> None:
        if receipt["status"] != "synced":
            return
        ledger = self._read(anchor, self._name(identity, ".ledger.json"))
        if ledger is None:
            raise SyntheticSyncError("Synthetic confirmation is unavailable; reconcile")
        self._ledger(ledger, identity)
        if ledger["synthetic_id"] != receipt["synthetic_id"]:
            raise SyntheticSyncError(
                "Synthetic confirmation is inconsistent; reconcile"
            )

    @staticmethod
    def _synthetic_id(value: Any) -> None:
        try:
            if not isinstance(value, str) or not value.startswith("SYNTHETIC-"):
                raise ValueError
            identifier = value.removeprefix("SYNTHETIC-")
            if str(UUID(identifier)) != identifier:
                raise ValueError
        except (ValueError, AttributeError):
            raise SyntheticSyncError("Stored synthetic identity is invalid") from None

    def deliver(
        self,
        payload: dict[str, Any],
        outcome: Literal["success", "failed", "unknown"] = "success",
    ) -> dict[str, Any]:
        if outcome not in {"success", "failed", "unknown"}:
            raise SyntheticSyncError("Unsupported synthetic outcome")
        identity = delivery_identity(payload)
        with AnchoredDirectory(self.root) as anchor, anchor.lock("sync.lock"):
            name = self._name(identity, ".receipt.json")
            prior = self._read(anchor, name)
            if prior is not None:
                self._validate(prior, identity)
                if prior["status"] == "synced":
                    self._confirmed(anchor, prior, identity)
                    return prior
                if prior["status"] in {"unknown", "pending"}:
                    raise SyntheticSyncError(
                        "Reconcile the unconfirmed attempt before retrying"
                    )
            receipt = {
                "identity": identity,
                "status": "pending",
                "mode": "synthetic",
                "live_synced": False,
                "attempt": prior["attempt"] + 1 if prior else 1,
                "actor": f"local operator, uid={os.geteuid()}",
                "timestamp": datetime.now(UTC).isoformat(),
                "synthetic_id": None,
            }
            self._write(anchor, name, receipt)
            if outcome != "failed":
                # Simulate delivery followed by lost acknowledgement.
                ledger = {
                    "identity": identity,
                    "synthetic_id": "SYNTHETIC-" + str(uuid4()),
                }
                existing = self._read(anchor, self._name(identity, ".ledger.json"))
                if existing is not None:
                    self._ledger(existing, identity)
                    ledger = existing
                else:
                    self._write(anchor, self._name(identity, ".ledger.json"), ledger)
                if outcome == "success":
                    receipt["synthetic_id"] = ledger["synthetic_id"]
            receipt["status"] = {
                "success": "synced",
                "failed": "failed",
                "unknown": "unknown",
            }[outcome]
            self._write(anchor, name, receipt)
            return receipt

    def reconcile(self, payload: dict[str, Any]) -> dict[str, Any]:
        identity = delivery_identity(payload)
        with AnchoredDirectory(self.root) as anchor, anchor.lock("sync.lock"):
            name = self._name(identity, ".receipt.json")
            receipt = self._read(anchor, name)
            if receipt is None:
                raise SyntheticSyncError("No synthetic attempt exists")
            self._validate(receipt, identity)
            ledger = self._read(anchor, self._name(identity, ".ledger.json"))
            if ledger is not None:
                self._ledger(ledger, identity)
                receipt["status"] = "synced"
                receipt["synthetic_id"] = ledger["synthetic_id"]
            elif receipt["status"] in {"unknown", "pending"}:
                receipt["status"] = "failed"
            elif receipt["status"] == "synced":
                raise SyntheticSyncError(
                    "Synthetic confirmation ledger is missing; recovery is required"
                )
            receipt["timestamp"] = datetime.now(UTC).isoformat()
            self._write(anchor, name, receipt)
            return receipt
