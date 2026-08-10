"""Metadata-first, approved-root Local Files connector."""

from __future__ import annotations

import hashlib
import mimetypes
import os
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

from edn.connectors import (
    Checkpoint,
    ConnectorManifest,
    ConnectorPlan,
    ConnectorRequest,
    DiscoveryResult,
    IncompatibleSourceStateError,
    IngestResult,
    InspectionResult,
    ResourceCandidate,
    SourceUnavailableError,
    VerificationResult,
    VerificationStatus,
)
from edn.connectors.local_files.catalogue import CandidateCatalogue
from edn.connectors.local_files.config import (
    ApprovedRoot,
    LocalFilesConfig,
    SymlinkPolicy,
)
from edn.connectors.local_files.fingerprint import content_sha256, metadata_fingerprint
from edn.connectors.local_files.models import CandidateState, FileCandidate
from edn.connectors.local_files.traversal import (
    DurableTraversal,
    IncompatibleTraversalStateError,
    TraversalAccessError,
)
from edn.core import (
    CapabilityManifest,
    CapabilityStatus,
    EvidenceRef,
    SourceRef,
    UniversalRecordRef,
)
from edn.core.registry import AuthenticationStatus, CapabilityRuntimeState

CONNECTOR_ID = "local-files"
CONNECTOR_VERSION = "1.0.0"
SUPPORTED_TEXT_EXTENSIONS = frozenset({".txt", ".md", ".json", ".csv"})

_CATEGORY_EXTENSIONS = {
    "document": frozenset({".doc", ".docx", ".odt", ".rtf"}),
    "spreadsheet": frozenset({".xls", ".xlsx", ".ods"}),
    "presentation": frozenset({".ppt", ".pptx", ".odp"}),
    "pdf": frozenset({".pdf"}),
    "email_archive": frozenset({".pst", ".ost"}),
    "mailbox": frozenset({".mbox"}),
    "text": frozenset({".txt", ".md"}),
    "structured_data": frozenset({".json", ".csv", ".xml", ".yaml", ".yml"}),
    "database": frozenset({".db", ".sqlite", ".sqlite3"}),
    "image": frozenset({".jpg", ".jpeg", ".png", ".gif", ".tiff", ".webp"}),
    "video": frozenset({".mp4", ".mov", ".avi", ".mkv"}),
    "audio": frozenset({".mp3", ".wav", ".flac", ".m4a"}),
    "archive": frozenset({".zip", ".7z", ".tar", ".gz"}),
    "source_code": frozenset({".py", ".js", ".ts", ".cs", ".java", ".go", ".rs"}),
    "executable": frozenset({".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh"}),
}
_MISSING_CAPABILITIES = {
    "document": "document-docx.ingest",
    "spreadsheet": "spreadsheet.ingest",
    "presentation": "presentation.ingest",
    "pdf": "document-pdf.ingest",
    "email_archive": "outlook-archive.ingest",
    "mailbox": "email-memory.ingest",
    "database": "database.inspect",
    "image": "image.ingest",
    "video": "video.ingest",
    "audio": "audio.ingest",
    "archive": "archive.inspect",
    "source_code": "source-code.ingest",
    "executable": "executable.prohibited",
    "unknown": "local-files.unsupported.ingest",
}


class LocalFilesConnector:
    def __init__(self, config: LocalFilesConfig) -> None:
        if not config.metadata_only_discovery:
            raise ValueError("Local Files v0.1 requires metadata-only discovery")
        self.config = config
        self.catalogue = CandidateCatalogue(config.catalogue_path)
        self.catalogue.initialise()
        domains = frozenset(root.security_domain.domain_id for root in config.roots)
        capabilities = tuple(
            CapabilityManifest(
                capability_id,
                "local-filesystem",
                CONNECTOR_ID,
                CONNECTOR_VERSION,
                frozenset({operation}),
                frozenset({permission}),
                domains,
                risk,
            )
            for capability_id, operation, permission, risk in (
                (
                    "local-files.discover",
                    "discover",
                    "filesystem.metadata.read",
                    "read",
                ),
                ("local-files.inspect", "inspect", "filesystem.metadata.read", "read"),
                ("local-files.plan", "plan", "filesystem.metadata.read", "draft"),
                ("local-files.ingest", "ingest", "filesystem.content.read", "ingest"),
                ("local-files.verify", "verify", "filesystem.content.read", "read"),
            )
        )
        self._manifest = ConnectorManifest(
            CONNECTOR_ID,
            CONNECTOR_VERSION,
            "Local Files",
            "local-filesystem",
            "Approved-root metadata discovery and controlled text ingestion.",
            "filesystem",
            capabilities,
            frozenset({"discover", "inspect", "plan", "ingest", "verify"}),
            "urn:edn:schema:local-files-config:1",
            "1.0.0",
        )

    @property
    def manifest(self) -> ConnectorManifest:
        return self._manifest

    def runtime_states(
        self, status: CapabilityStatus = CapabilityStatus.READY
    ) -> tuple[tuple[CapabilityManifest, CapabilityRuntimeState], ...]:
        return tuple(
            (
                capability,
                CapabilityRuntimeState(
                    status,
                    AuthenticationStatus.NOT_REQUIRED,
                    health="healthy" if status is CapabilityStatus.READY else "unknown",
                    explanation="Local configuration supplied and validated.",
                ),
            )
            for capability in self.manifest.capabilities
        )

    def discover(
        self, request: ConnectorRequest, checkpoint: Checkpoint | None = None
    ) -> DiscoveryResult:
        root_ids = request.scope or tuple(root.root_id for root in self.config.roots)
        roots = tuple(self.config.root(root_id) for root_id in root_ids)
        if any(root.security_domain != request.security_domain for root in roots):
            raise SourceUnavailableError(
                "Requested roots do not match the active domain."
            )
        self.catalogue.begin_run(request.correlation_id, len(roots))
        durable = 0 if checkpoint is None else checkpoint.durable_items
        candidates: list[FileCandidate] = []
        warnings: list[str] = []
        cursor_state = None
        if checkpoint is not None:
            cursor_state = self.catalogue.traversal_cursor(
                checkpoint.resume_marker,
                request.correlation_id,
                self.config.configuration_hash,
                CONNECTOR_VERSION,
            )
        try:
            traversal = DurableTraversal(roots, state=cursor_state)
            excluded = 0
            while len(candidates) < self.config.discovery_batch_size:
                try:
                    item = traversal.next_path()
                except TraversalAccessError as error:
                    warnings.append(f"inaccessible:{error.error_type}")
                    traversal.skip_inaccessible_directory()
                    excluded += 1
                    continue
                if item is None:
                    break
                root, path, root_device, is_directory = item
                if is_directory:
                    root_path = root.path.resolve(strict=True)
                    depth = len(path.relative_to(root_path).parts)
                    if not self._allow_directory(path, root_path, root_device, depth):
                        traversal.skip_current_directory()
                        excluded += 1
                    continue
                candidate = self._candidate(
                    path,
                    root,
                    request.correlation_id,
                    root.path.resolve(strict=True),
                    root_device,
                )
                if candidate is None:
                    excluded += 1
                else:
                    candidates.append(candidate)
        except IncompatibleTraversalStateError as error:
            raise IncompatibleSourceStateError(str(error)) from error
        persisted = tuple(candidates)
        self.catalogue.upsert_many(persisted)
        self.catalogue.add_excluded(request.correlation_id, excluded)
        processed = durable + len(persisted)
        if not traversal.complete:
            cursor_seed = f"{request.correlation_id}:{processed}".encode()
            cursor_id = f"cursor:{hashlib.sha256(cursor_seed).hexdigest()}"
            self.catalogue.save_traversal_cursor(
                cursor_id,
                request.correlation_id,
                self.config.configuration_hash,
                CONNECTOR_VERSION,
                traversal.to_json(),
            )
            next_checkpoint = Checkpoint(
                f"checkpoint:{hashlib.sha256(f'{request.correlation_id}:{processed}'.encode()).hexdigest()}",
                CONNECTOR_ID,
                CONNECTOR_VERSION,
                self.config.configuration_hash,
                "discover",
                root_ids,
                cursor_id,
                processed,
                datetime.now(UTC),
            )
        else:
            next_checkpoint = None
            self.catalogue.complete_run(request.correlation_id)
        resources = tuple(self._resource(candidate) for candidate in persisted)
        return DiscoveryResult(
            request.request_id,
            resources,
            tuple(warnings),
            next_checkpoint,
            processed,
            traversal.complete,
        )

    def inspect(self, request: ConnectorRequest) -> InspectionResult:
        if len(request.scope) != 1:
            raise ValueError("inspect requires exactly one candidate ID")
        candidate = self._authorized_candidate(request.scope[0], request)
        return InspectionResult(
            request.request_id,
            self._resource(candidate),
            (
                f"category:{candidate.category}",
                f"fingerprint:metadata_sha256:{candidate.metadata_fingerprint}",
                "ingestion:"
                + ("supported" if candidate.supported_ingestion else "missing_adapter"),
            ),
        )

    def plan(self, request: ConnectorRequest) -> ConnectorPlan:
        if not request.scope:
            raise ValueError("ingestion plan requires exact candidate IDs")
        candidates = tuple(
            self._authorized_candidate(identifier, request)
            for identifier in request.scope
        )
        self.catalogue.mark_selected(request.scope)
        supported = tuple(item for item in candidates if item.supported_ingestion)
        unsupported = tuple(item for item in candidates if not item.supported_ingestion)
        categories = ",".join(sorted({item.category for item in candidates}))
        mutations = (
            f"read-supported-files:{len(supported)}",
            f"defer-unsupported-files:{len(unsupported)}",
            f"categories:{categories}",
        )
        return ConnectorPlan(
            f"plan:{hashlib.sha256(':'.join(sorted(request.scope)).encode()).hexdigest()}",
            CONNECTOR_ID,
            CONNECTOR_VERSION,
            "local-files.ingest",
            "ingest",
            tuple(sorted(request.scope)),
            ("filesystem.content.read",),
            mutations,
            "ingest",
            (),
            True,
            len(candidates),
            sum(item.size_bytes for item in supported),
            self.config.configuration_hash,
        )

    def ingest(
        self, request: ConnectorRequest, checkpoint: Checkpoint | None = None
    ) -> IngestResult:
        candidates = tuple(
            self._authorized_candidate(identifier, request)
            for identifier in sorted(request.scope)
        )
        marker = "" if checkpoint is None else checkpoint.resume_marker
        durable = 0 if checkpoint is None else checkpoint.durable_items
        remaining = tuple(item for item in candidates if item.resource_id > marker)
        batch = remaining[: self.config.ingestion_batch_size]
        records: list[UniversalRecordRef] = []
        for candidate in batch:
            if not candidate.supported_ingestion:
                continue
            try:
                path = self.config.validate_candidate_path(
                    candidate.path, candidate.root_id
                )
                stat = path.stat()
            except (OSError, ValueError) as error:
                raise SourceUnavailableError(
                    "An approved source file is no longer accessible."
                ) from error
            current = metadata_fingerprint(
                path, size=stat.st_size, modified_ns=stat.st_mtime_ns
            )
            if current.value != candidate.metadata_fingerprint:
                self.catalogue.mark_source_changed(candidate.resource_id)
                raise IncompatibleSourceStateError(
                    "An approved source file changed after planning."
                )
            fingerprint = content_sha256(path)
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise SourceUnavailableError(
                    "An approved text file could not be read safely."
                ) from error
            self._store_content(fingerprint.value, content)
            source = SourceRef(
                f"local-files.{candidate.root_id}",
                CONNECTOR_ID,
                candidate.root_id,
                "Local Files approved root",
            )
            record = UniversalRecordRef(
                source,
                candidate.resource_id,
                candidate.security_domain,
                candidate.classification,
                "file.text",
                candidate.path.as_uri(),
                fingerprint.value,
            )
            self.catalogue.mark_ingested(
                candidate.resource_id, record, fingerprint.value
            )
            records.append(record)
        processed = durable + len(batch)
        complete = len(batch) == len(remaining)
        if complete:
            next_checkpoint = None
        else:
            last_id = batch[-1].resource_id
            next_checkpoint = Checkpoint(
                f"checkpoint:{hashlib.sha256(f'{request.correlation_id}:{processed}'.encode()).hexdigest()}",
                CONNECTOR_ID,
                CONNECTOR_VERSION,
                self.config.configuration_hash,
                "ingest",
                request.scope,
                last_id,
                processed,
                datetime.now(UTC),
            )
        return IngestResult(
            request.request_id,
            tuple(records),
            next_checkpoint,
            processed,
            len(candidates),
            complete,
        )

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        if request.operation == "discover":
            complete = self.catalogue.run_complete(request.correlation_id)
            return VerificationResult(
                request.request_id,
                VerificationStatus.VERIFIED
                if complete
                else VerificationStatus.INDETERMINATE,
                "Discovery catalogue completion was checked.",
            )
        candidates = tuple(
            self._authorized_candidate(identifier, request)
            for identifier in request.scope
        )
        supported = tuple(item for item in candidates if item.supported_ingestion)
        records = self.catalogue.records(tuple(item.resource_id for item in supported))
        if len(records) != len(supported):
            return VerificationResult(
                request.request_id,
                VerificationStatus.FAILED,
                "Not all supported approved files produced record references.",
                len(supported),
                len(records),
            )
        warnings = tuple(
            f"unsupported:{item.category}"
            for item in candidates
            if not item.supported_ingestion
        )
        return VerificationResult(
            request.request_id,
            VerificationStatus.VERIFIED_WITH_WARNINGS
            if warnings
            else VerificationStatus.VERIFIED,
            "Approved Local Files ingestion was reconciled.",
            len(supported),
            len(records),
            warnings,
        )

    def evidence(self, resource_ids: Sequence[str]) -> tuple[EvidenceRef, ...]:
        evidence = []
        for candidate in self.catalogue.selected(resource_ids):
            if candidate.record is not None:
                evidence.append(
                    EvidenceRef(
                        f"evidence:{candidate.resource_id.removeprefix('file:')}",
                        candidate.record,
                        locator="full-text",
                        transformation_id="local-files.text",
                        transformation_version=CONNECTOR_VERSION,
                        content_hash=candidate.content_hash,
                    )
                )
        return tuple(evidence)

    def _walk_roots(
        self,
        roots: Sequence[ApprovedRoot],
        run_id: str,
        warnings: list[str],
    ) -> Iterator[FileCandidate]:
        for root in sorted(roots, key=lambda item: item.root_id):
            root_path = root.path.resolve(strict=True)
            root_device = root_path.stat().st_dev

            def on_error(error: OSError) -> None:
                warnings.append(f"inaccessible:{type(error).__name__}")

            for directory, directory_names, filenames in os.walk(
                root_path, topdown=True, followlinks=False, onerror=on_error
            ):
                current = Path(directory)
                depth = len(current.relative_to(root_path).parts)
                directory_names[:] = sorted(
                    name
                    for name in directory_names
                    if self._allow_directory(
                        current / name, root_path, root_device, depth + 1
                    )
                )
                for filename in sorted(filenames):
                    path = current / filename
                    candidate = self._candidate(
                        path, root, run_id, root_path, root_device
                    )
                    if candidate is not None:
                        yield candidate

    def _allow_directory(
        self, path: Path, root: Path, root_device: int, depth: int
    ) -> bool:
        if self.config.max_depth is not None and depth > self.config.max_depth:
            return False
        if not self.config.discover_hidden and _is_hidden(path):
            return False
        if any(_is_within(path, excluded) for excluded in self.config.excluded_roots):
            return False
        if path.is_symlink():
            return False
        try:
            resolved = path.resolve(strict=True)
            return _is_within(resolved, root) and (
                not self.config.stay_on_filesystem
                or resolved.stat().st_dev == root_device
            )
        except OSError:
            return False

    def _candidate(
        self,
        path: Path,
        root: ApprovedRoot,
        run_id: str,
        root_path: Path,
        root_device: int,
    ) -> FileCandidate | None:
        extension = path.suffix.casefold()
        if extension in self.config.excluded_extensions:
            return None
        if (
            self.config.allowed_extensions
            and extension not in self.config.allowed_extensions
        ):
            return None
        if not self.config.discover_hidden and _is_hidden(path):
            return None
        symlink = path.is_symlink()
        if symlink and self.config.symlink_policy is SymlinkPolicy.NEVER:
            return None
        try:
            resolved = path.resolve(strict=True)
            if not _is_within(resolved, root_path):
                return None
            stat = resolved.stat()
            if self.config.stay_on_filesystem and stat.st_dev != root_device:
                return None
            if not resolved.is_file():
                return None
        except OSError:
            return None
        category = classify_extension(extension)
        supported = (
            extension in SUPPORTED_TEXT_EXTENSIONS
            and stat.st_size <= self.config.max_file_size_bytes
        )
        missing = (
            None
            if supported
            else _MISSING_CAPABILITIES.get(category, "local-files.unsupported.ingest")
        )
        fingerprint = metadata_fingerprint(
            resolved, size=stat.st_size, modified_ns=stat.st_mtime_ns
        )
        resource_id = f"file:{hashlib.sha256(str(resolved).encode()).hexdigest()}"
        state = CandidateState.DISCOVERED if supported else CandidateState.UNSUPPORTED
        return FileCandidate(
            run_id,
            resource_id,
            root.root_id,
            resolved,
            path.name,
            extension,
            category,
            mimetypes.guess_type(path.name, strict=False)[0],
            stat.st_size,
            datetime.fromtimestamp(stat.st_mtime, UTC),
            datetime.fromtimestamp(stat.st_ctime, UTC),
            _is_hidden(path),
            symlink,
            root.security_domain,
            root.classification,
            fingerprint.value,
            supported,
            missing,
            state,
        )

    def _authorized_candidate(
        self, resource_id: str, request: ConnectorRequest
    ) -> FileCandidate:
        candidate = self.catalogue.get(resource_id)
        if candidate is None:
            raise ValueError("unknown Local Files candidate")
        if (
            candidate.security_domain != request.security_domain
            or candidate.classification != request.classification
        ):
            raise SourceUnavailableError(
                "Candidate security context does not match the request."
            )
        self.config.validate_candidate_path(candidate.path, candidate.root_id)
        return candidate

    @staticmethod
    def _resource(candidate: FileCandidate) -> ResourceCandidate:
        return ResourceCandidate(
            candidate.resource_id,
            candidate.category,
            candidate.path.as_uri(),
            candidate.security_domain,
            candidate.classification,
            candidate.size_bytes,
            candidate.modified_at,
            "heuristic_supported" if candidate.supported_ingestion else "unknown",
            candidate.state is CandidateState.INGESTED,
            ("filesystem.metadata.read",),
            candidate.warnings,
        )

    def _store_content(self, content_hash: str, content: str) -> None:
        directory = self.config.content_store_path / content_hash[:2]
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{content_hash}.txt"
        if target.exists():
            return
        temporary = directory / f".{content_hash}.tmp"
        try:
            with temporary.open("x", encoding="utf-8", newline="") as destination:
                destination.write(content)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()


def classify_extension(extension: str) -> str:
    for category, extensions in _CATEGORY_EXTENSIONS.items():
        if extension in extensions:
            return category
    return "unknown"


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True
