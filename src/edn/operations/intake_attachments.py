"""Linux-only protected local intake originals; no extraction or cloud dispatch."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID, uuid4

from edn.operations.intake_formats import (
    MAX_ATTACHMENT_BYTES as MAX_ATTACHMENT_BYTES,
)
from edn.operations.intake_formats import (
    MAX_METADATA_BYTES as MAX_METADATA_BYTES,
)
from edn.operations.intake_formats import (
    MAX_REQUEST_BYTES as MAX_REQUEST_BYTES,
)
from edn.operations.intake_formats import (
    MAX_REQUEST_FILES as MAX_REQUEST_FILES,
)
from edn.operations.intake_formats import (
    MEDIA_TYPES,
    normalize_attachment_name,
)
from edn.operations.intake_formats import (
    IntakeAttachmentError as IntakeAttachmentError,
)
from edn.operations.intake_formats import (
    validate_attachment_payload as validate_attachment_payload,
)
from edn.operations.intake_security import AnchoredDirectory, require_supported_platform


def _uuid(value: str) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise IntakeAttachmentError("Attachment identity is invalid.") from None
    return value


@dataclass(frozen=True, slots=True)
class IntakeAttachment:
    attachment_id: str
    request_id: str
    original_name: str
    media_type: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _uuid(self.attachment_id)
        _uuid(self.request_id)
        if (
            normalize_attachment_name(self.original_name) != self.original_name
            or MEDIA_TYPES.get(Path(self.original_name).suffix.casefold())
            != self.media_type
        ):
            raise IntakeAttachmentError("Attachment metadata is invalid.")
        if (
            type(self.size_bytes) is not int
            or not 1 <= self.size_bytes <= MAX_ATTACHMENT_BYTES
        ):
            raise IntakeAttachmentError("Attachment metadata is invalid.")
        if (
            not isinstance(self.sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
        ):
            raise IntakeAttachmentError("Attachment metadata is invalid.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_regular(directory: AnchoredDirectory, name: str, limit: int) -> bytes:
    descriptor = directory.open_file(name)
    with os.fdopen(descriptor, "rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise IntakeAttachmentError("Attachment exceeds the supported limit.")
    return payload


def _stage_file(directory: AnchoredDirectory, name: str, payload: bytes) -> None:
    descriptor = directory.open_file(name, create=True, write=True)
    with os.fdopen(descriptor, "wb") as stream:
        if stream.write(payload) != len(payload):
            raise OSError("Incomplete protected write")
        stream.flush()
        os.fsync(stream.fileno())
        info = os.fstat(stream.fileno())
        if (
            info.st_size != len(payload)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise IntakeAttachmentError("Attachment staging protection is invalid.")


def _publish_file(directory: AnchoredDirectory, name: str, payload: bytes) -> None:
    pending = ".pending-" + str(uuid4())
    try:
        _stage_file(directory, pending, payload)
        directory.publish(pending, name)
        os.fsync(directory.fd)
    finally:
        if directory.exists(pending):
            directory.unlink(pending)


class IntakeAttachmentStore:
    """Descriptor-anchored originals with locked conservative quota reservations."""

    def __init__(self, root: Path) -> None:
        require_supported_platform()  # Before any path inspection/create/write.
        # The lexical Git check is preflight only; no data path syscalls follow it.
        if any((parent / ".git").exists() for parent in (root, *root.parents)):
            raise IntakeAttachmentError("Attachment originals must stay outside Git.")
        try:
            with AnchoredDirectory(root):
                pass
        except OSError:
            raise IntakeAttachmentError("Attachment storage is unavailable.") from None
        self.root = root
        self.recover()

    @staticmethod
    def _names(directory: AnchoredDirectory, limit: int = 2100) -> list[str]:
        names: list[str] = []
        with os.scandir(directory.fd) as entries:
            for entry in entries:
                if len(names) >= limit:
                    raise IntakeAttachmentError(
                        "Attachment recovery exceeds its bounded limit."
                    )
                names.append(entry.name)
        return names

    @staticmethod
    def _pending(name: str) -> bool:
        for prefix in (".pending-", ".quota-"):
            if name.startswith(prefix):
                try:
                    _uuid(name.removeprefix(prefix))
                    return True
                except IntakeAttachmentError:
                    return False
        return False

    @staticmethod
    def _validate_entries(entries: Any) -> None:
        if not isinstance(entries, list) or len(entries) > MAX_REQUEST_FILES:
            raise IntakeAttachmentError("Attachment receipt entries are invalid.")
        seen: set[str] = set()
        total = 0
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "attachment_id",
                "size_bytes",
                "state",
            }:
                raise IntakeAttachmentError("Attachment receipt entries are invalid.")
            _uuid(entry["attachment_id"])
            if (
                entry["attachment_id"] in seen
                or type(entry["size_bytes"]) is not int
                or not 1 <= entry["size_bytes"] <= MAX_ATTACHMENT_BYTES
                or entry["state"] not in {"reserved", "complete"}
            ):
                raise IntakeAttachmentError("Attachment receipt entries are invalid.")
            seen.add(entry["attachment_id"])
            total += entry["size_bytes"]
        if total > MAX_REQUEST_BYTES:
            raise IntakeAttachmentError("Attachment receipt exceeds its quota.")

    def recover(self) -> None:
        """Quarantine interrupted reservations at startup; never delete originals."""
        require_supported_platform()
        try:
            with AnchoredDirectory(self.root) as root:
                requests: list[str] = []
                for name in self._names(root):
                    try:
                        _uuid(name)
                    except IntakeAttachmentError:
                        continue
                    requests.append(name)
                    if len(requests) > 1000:
                        raise IntakeAttachmentError(
                            "Attachment recovery exceeds its bounded limit."
                        )
                for request_id in requests:
                    with (
                        root.lock(request_id + ".lock"),
                        root.child(request_id) as request,
                    ):
                        self._recover_request(root, request, request_id)
        except OSError:
            raise IntakeAttachmentError(
                "Attachment recovery could not be committed."
            ) from None
        except (ValueError, TypeError, RecursionError) as error:
            if isinstance(error, IntakeAttachmentError):
                raise
            raise IntakeAttachmentError(
                "Attachment recovery metadata is invalid."
            ) from None

    def _journal(self, request: AnchoredDirectory, payload: dict[str, Any]) -> None:
        pending = ".quota-" + str(uuid4())
        content = json.dumps(payload, sort_keys=True).encode("utf-8")
        if len(content) > MAX_METADATA_BYTES:
            raise IntakeAttachmentError(
                "Attachment recovery exceeds its bounded limit."
            )
        try:
            _stage_file(request, pending, content)
            request.replace(pending, ".recovery.json")
            os.fsync(request.fd)
        finally:
            if request.exists(pending):
                request.unlink(pending)

    def _recover_request(
        self, root: AnchoredDirectory, request: AnchoredDirectory, request_id: str
    ) -> None:
        resumed = request.exists(".recovery.json")
        self._recover_request_once(root, request, request_id)
        if resumed:
            # Process death can leave quota stages created after the saved plan.
            # Finish that plan first, then perform one fresh bounded sweep.
            self._recover_request_once(root, request, request_id)

    def _recover_request_once(
        self, root: AnchoredDirectory, request: AnchoredDirectory, request_id: str
    ) -> None:
        if request.exists(".recovery.json"):
            plan = json.loads(
                _read_regular(request, ".recovery.json", MAX_METADATA_BYTES)
            )
        else:
            names = self._names(request, 301)
            if not request.exists("attachments.json"):
                if not names:
                    return
                entries: list[dict[str, Any]] = []
            else:
                entries = self._quota(request, request_id)
            complete = {
                entry["attachment_id"]
                for entry in entries
                if entry["state"] == "complete"
            }
            moves: list[dict[str, str]] = []
            for name in names:
                if name == "attachments.json" or name in complete:
                    continue
                if self._pending(name):
                    descriptor = request.open_file(name)
                    try:
                        if os.fstat(descriptor).st_size > MAX_METADATA_BYTES:
                            raise IntakeAttachmentError(
                                "Attachment recovery asset is invalid."
                            )
                    finally:
                        os.close(descriptor)
                    kind = "file"
                else:
                    _uuid(name)
                    with request.child(name) as folder:
                        for member in self._names(folder, 10):
                            if member not in {
                                "original.bin",
                                "metadata.json",
                            } and not self._pending(member):
                                raise IntakeAttachmentError(
                                    "Attachment recovery asset is invalid."
                                )
                            descriptor = folder.open_file(member)
                            try:
                                if os.fstat(descriptor).st_size > MAX_ATTACHMENT_BYTES:
                                    raise IntakeAttachmentError(
                                        "Attachment recovery asset is invalid."
                                    )
                            finally:
                                os.close(descriptor)
                    kind = "directory"
                moves.append(
                    {"source": name, "target": f"asset-{len(moves):03d}", "kind": kind}
                )
            kept = [entry for entry in entries if entry["state"] == "complete"]
            if not moves and kept == entries:
                return
            plan = {
                "schema_version": 1,
                "request_id": request_id,
                "recovery_id": str(uuid4()),
                "old_entries": entries,
                "new_entries": kept,
                "moves": moves,
            }
            self._journal(request, plan)
        if (
            not isinstance(plan, dict)
            or set(plan)
            != {
                "schema_version",
                "request_id",
                "recovery_id",
                "old_entries",
                "new_entries",
                "moves",
            }
            or type(plan["schema_version"]) is not int
            or plan["schema_version"] != 1
            or plan["request_id"] != request_id
        ):
            raise IntakeAttachmentError("Attachment recovery journal is invalid.")
        _uuid(plan["recovery_id"])
        for key in ("old_entries", "new_entries"):
            self._validate_entries(plan[key])
        if plan["new_entries"] != [
            entry for entry in plan["old_entries"] if entry["state"] == "complete"
        ]:
            raise IntakeAttachmentError("Attachment recovery journal is invalid.")
        moves = plan["moves"]
        if not isinstance(moves, list) or len(moves) > 300:
            raise IntakeAttachmentError("Attachment recovery journal is invalid.")
        current = (
            self._quota(request, request_id)
            if request.exists("attachments.json")
            else []
        )
        if current not in (plan["old_entries"], plan["new_entries"]):
            raise IntakeAttachmentError("Attachment recovery receipt changed.")
        with (
            root.child(".quarantine", create=True) as quarantine,
            quarantine.child(request_id, create=True) as request_archive,
            request_archive.child(plan["recovery_id"], create=True) as archive,
        ):
            seen: set[str] = set()
            for index, move in enumerate(moves):
                if (
                    not isinstance(move, dict)
                    or set(move) != {"source", "target", "kind"}
                    or move["target"] != f"asset-{index:03d}"
                    or move["kind"] not in {"file", "directory"}
                    or move["source"] in seen
                ):
                    raise IntakeAttachmentError(
                        "Attachment recovery journal is invalid."
                    )
                if move["kind"] == "file":
                    if not self._pending(move["source"]):
                        raise IntakeAttachmentError(
                            "Attachment recovery journal is invalid."
                        )
                else:
                    _uuid(move["source"])
                    if any(
                        entry["attachment_id"] == move["source"]
                        and entry["state"] == "complete"
                        for entry in plan["old_entries"]
                    ):
                        raise IntakeAttachmentError(
                            "Completed attachments cannot be quarantined."
                        )
                seen.add(move["source"])
                if request.exists(move["source"]):
                    if archive.exists(move["target"]):
                        raise IntakeAttachmentError(
                            "Attachment quarantine target already exists."
                        )
                    request.move_to(move["source"], archive, move["target"])
                    os.fsync(request.fd)
                    os.fsync(archive.fd)
                elif not archive.exists(move["target"]):
                    raise IntakeAttachmentError(
                        "Attachment quarantine asset is missing."
                    )
            self._save_quota(request, request_id, plan["new_entries"])
            request.move_to(".recovery.json", archive, "sweep.json")
            os.fsync(request.fd)
            os.fsync(archive.fd)

    def _quota(
        self, request: AnchoredDirectory, request_id: str
    ) -> list[dict[str, Any]]:
        if not request.exists("attachments.json"):
            if os.listdir(request.fd):
                raise IntakeAttachmentError("Attachment storage requires recovery.")
            return []
        try:
            value = json.loads(
                _read_regular(request, "attachments.json", MAX_METADATA_BYTES)
            )
            if (
                not isinstance(value, dict)
                or set(value) != {"schema_version", "request_id", "entries"}
                or type(value["schema_version"]) is not int
                or value["schema_version"] != 1
                or value["request_id"] != request_id
            ):
                raise ValueError
            entries = value["entries"]
            if not isinstance(entries, list) or len(entries) > MAX_REQUEST_FILES:
                raise ValueError
            seen: set[str] = set()
            total = 0
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {
                    "attachment_id",
                    "size_bytes",
                    "state",
                }:
                    raise ValueError
                _uuid(entry["attachment_id"])
                if (
                    entry["attachment_id"] in seen
                    or type(entry["size_bytes"]) is not int
                    or not 1 <= entry["size_bytes"] <= MAX_ATTACHMENT_BYTES
                    or entry["state"] not in {"reserved", "complete"}
                ):
                    raise ValueError
                seen.add(entry["attachment_id"])
                total += entry["size_bytes"]
            if total > MAX_REQUEST_BYTES:
                raise ValueError
            return entries
        except (OSError, ValueError, TypeError, RecursionError):
            raise IntakeAttachmentError(
                "Attachment quota metadata is invalid."
            ) from None

    def _save_quota(
        self, request: AnchoredDirectory, request_id: str, entries: list[dict[str, Any]]
    ) -> None:
        if request.exists("attachments.json"):
            descriptor = request.open_file("attachments.json")
            os.close(descriptor)
        pending = ".quota-" + str(uuid4())
        content = json.dumps(
            {"schema_version": 1, "request_id": request_id, "entries": entries},
            sort_keys=True,
        ).encode("utf-8")
        if len(content) > MAX_METADATA_BYTES:
            raise IntakeAttachmentError("Attachment quota metadata exceeds its limit.")
        try:
            _stage_file(request, pending, content)
            request.replace(pending, "attachments.json")
            os.fsync(request.fd)
        finally:
            if request.exists(pending):
                request.unlink(pending)

    @staticmethod
    def _metadata(
        folder: AnchoredDirectory, request_id: str, attachment_id: str
    ) -> IntakeAttachment:
        try:
            value = json.loads(
                _read_regular(folder, "metadata.json", MAX_METADATA_BYTES)
            )
            if not isinstance(value, dict) or set(value) != {
                "attachment_id",
                "request_id",
                "original_name",
                "media_type",
                "size_bytes",
                "sha256",
            }:
                raise ValueError
            record = IntakeAttachment(**value)
            if (record.request_id, record.attachment_id) != (request_id, attachment_id):
                raise ValueError
            return record
        except (OSError, ValueError, TypeError, RecursionError):
            raise IntakeAttachmentError(
                "Attachment metadata is unavailable or invalid."
            ) from None

    def _physical(
        self, request: AnchoredDirectory, request_id: str, entries: list[dict[str, Any]]
    ) -> None:
        allowed = {entry["attachment_id"] for entry in entries} | {"attachments.json"}
        if any(name not in allowed for name in os.listdir(request.fd)):
            raise IntakeAttachmentError("Attachment storage requires recovery.")
        for entry in entries:
            if not request.exists(entry["attachment_id"]):
                if entry["state"] == "complete":
                    raise IntakeAttachmentError("Attachment storage requires recovery.")
                continue
            with request.child(entry["attachment_id"]) as folder:
                names = os.listdir(folder.fd)
                if any(name not in {"original.bin", "metadata.json"} for name in names):
                    raise IntakeAttachmentError("Attachment storage requires recovery.")
                for name in names:
                    descriptor = folder.open_file(name)
                    try:
                        info = os.fstat(descriptor)
                        cap = (
                            MAX_METADATA_BYTES
                            if name == "metadata.json"
                            else entry["size_bytes"]
                        )
                        if info.st_size > cap:
                            raise IntakeAttachmentError(
                                "Attachment physical quota is inconsistent."
                            )
                    finally:
                        os.close(descriptor)
                if entry["state"] == "complete":
                    descriptor = folder.open_file("original.bin")
                    try:
                        if os.fstat(descriptor).st_size != entry["size_bytes"]:
                            raise IntakeAttachmentError(
                                "Attachment physical quota is inconsistent."
                            )
                    finally:
                        os.close(descriptor)
                    record = self._metadata(folder, request_id, entry["attachment_id"])
                    if record.size_bytes != entry["size_bytes"]:
                        raise IntakeAttachmentError(
                            "Attachment quota metadata is inconsistent."
                        )

    def attach(
        self, request_id: str, filename: str, payload: bytes
    ) -> IntakeAttachment:
        require_supported_platform()
        _uuid(request_id)
        name, media = validate_attachment_payload(filename, payload)
        record = IntakeAttachment(
            str(uuid4()),
            request_id,
            name,
            media,
            len(payload),
            hashlib.sha256(payload).hexdigest(),
        )
        try:
            with (
                AnchoredDirectory(self.root) as root,
                root.lock(request_id + ".lock"),
                root.child(request_id, create=True) as request,
            ):
                os.fsync(root.fd)
                self._recover_request(root, request, request_id)
                entries = self._quota(request, request_id)
                self._physical(request, request_id, entries)
                for entry in entries:
                    if entry["state"] != "complete":
                        continue
                    with request.child(entry["attachment_id"]) as existing:
                        previous = self._metadata(
                            existing, request_id, entry["attachment_id"]
                        )
                        if previous.sha256 == record.sha256:
                            original = _read_regular(
                                existing, "original.bin", MAX_ATTACHMENT_BYTES
                            )
                            if (
                                hashlib.sha256(original).hexdigest() != record.sha256
                                or len(original) != previous.size_bytes
                            ):
                                raise IntakeAttachmentError(
                                    "Stored attachment failed its integrity check."
                                )
                            return previous
                if (
                    len(entries) >= MAX_REQUEST_FILES
                    or sum(entry["size_bytes"] for entry in entries) + record.size_bytes
                    > MAX_REQUEST_BYTES
                ):
                    raise IntakeAttachmentError(
                        "Request attachments exceed 100,000,000 bytes or 100 files."
                    )
                if any(
                    entry["attachment_id"] == record.attachment_id for entry in entries
                ):
                    raise IntakeAttachmentError(
                        "Attachment could not be stored: identity already exists."
                    )
                reserved = [
                    *entries,
                    {
                        "attachment_id": record.attachment_id,
                        "size_bytes": record.size_bytes,
                        "state": "reserved",
                    },
                ]
                self._save_quota(request, request_id, reserved)
                with request.child(record.attachment_id, create=True) as folder:
                    os.fsync(request.fd)
                    _publish_file(folder, "original.bin", payload)
                    _publish_file(
                        folder,
                        "metadata.json",
                        json.dumps(record.to_dict(), sort_keys=True).encode("utf-8"),
                    )
                reserved[-1]["state"] = "complete"
                self._save_quota(request, request_id, reserved)
        except OSError:
            raise IntakeAttachmentError("Attachment could not be stored.") from None
        return record

    def attach_stream(
        self, request_id: str, filename: str, stream: BinaryIO
    ) -> IntakeAttachment:
        require_supported_platform()
        try:
            payload = stream.read(MAX_ATTACHMENT_BYTES + 1)
        except (OSError, ValueError):
            raise IntakeAttachmentError(
                "Attachment content could not be read."
            ) from None
        return self.attach(request_id, filename, payload)

    def get(self, request_id: str, attachment_id: str) -> IntakeAttachment:
        require_supported_platform()
        _uuid(request_id)
        _uuid(attachment_id)
        try:
            with (
                AnchoredDirectory(self.root) as root,
                root.child(request_id) as request,
            ):
                entries = self._quota(request, request_id)
                self._physical(request, request_id, entries)
                if not any(
                    entry["attachment_id"] == attachment_id
                    and entry["state"] == "complete"
                    for entry in entries
                ):
                    raise ValueError
                with request.child(attachment_id) as folder:
                    return self._metadata(folder, request_id, attachment_id)
        except (OSError, ValueError, TypeError):
            raise IntakeAttachmentError(
                "Attachment metadata is unavailable or invalid."
            ) from None

    def read(self, request_id: str, attachment_id: str) -> bytes:
        require_supported_platform()
        _uuid(request_id)
        _uuid(attachment_id)
        try:
            # One directory walk anchors receipt, metadata and bytes together.
            with (
                AnchoredDirectory(self.root) as root,
                root.child(request_id) as request,
            ):
                entries = self._quota(request, request_id)
                self._physical(request, request_id, entries)
                if not any(
                    entry["attachment_id"] == attachment_id
                    and entry["state"] == "complete"
                    for entry in entries
                ):
                    raise ValueError
                with request.child(attachment_id) as folder:
                    record = self._metadata(folder, request_id, attachment_id)
                    payload = _read_regular(
                        folder, "original.bin", MAX_ATTACHMENT_BYTES
                    )
        except (OSError, ValueError, TypeError):
            raise IntakeAttachmentError(
                "Attachment original is unavailable or invalid."
            ) from None
        if (
            len(payload) != record.size_bytes
            or hashlib.sha256(payload).hexdigest() != record.sha256
        ):
            raise IntakeAttachmentError(
                "Attachment original failed its integrity check."
            )
        validate_attachment_payload(record.original_name, payload)
        return payload
