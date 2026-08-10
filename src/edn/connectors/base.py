"""Small optional protocols for connector lifecycle capabilities."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from edn.connectors.models import (
    ActionResult,
    Checkpoint,
    ConnectorManifest,
    ConnectorPlan,
    ConnectorRequest,
    DiscoveryResult,
    IngestResult,
    InspectionResult,
    SearchResult,
    VerificationResult,
)


@runtime_checkable
class Connector(Protocol):
    @property
    def manifest(self) -> ConnectorManifest: ...


@runtime_checkable
class DiscoverableConnector(Protocol):
    def discover(
        self, request: ConnectorRequest, checkpoint: Checkpoint | None = None
    ) -> DiscoveryResult: ...


@runtime_checkable
class InspectableConnector(Protocol):
    def inspect(self, request: ConnectorRequest) -> InspectionResult: ...


@runtime_checkable
class PlannableConnector(Protocol):
    def plan(self, request: ConnectorRequest) -> ConnectorPlan: ...


@runtime_checkable
class AuthenticatableConnector(Protocol):
    def authenticate(self, request: ConnectorRequest) -> VerificationResult: ...


@runtime_checkable
class IngestibleConnector(Protocol):
    def ingest(
        self, request: ConnectorRequest, checkpoint: Checkpoint | None = None
    ) -> IngestResult: ...


@runtime_checkable
class SyncableConnector(Protocol):
    def sync(
        self, request: ConnectorRequest, checkpoint: Checkpoint | None = None
    ) -> IngestResult: ...


@runtime_checkable
class CheckpointingConnector(Protocol):
    def checkpoint(self, request: ConnectorRequest) -> Checkpoint: ...

    def resume(
        self, request: ConnectorRequest, checkpoint: Checkpoint
    ) -> IngestResult: ...


@runtime_checkable
class SearchableConnector(Protocol):
    def search(self, request: ConnectorRequest) -> SearchResult: ...


@runtime_checkable
class ActionConnector(Protocol):
    def act(
        self, request: ConnectorRequest, approved_plan: ConnectorPlan
    ) -> ActionResult: ...


@runtime_checkable
class VerifiableConnector(Protocol):
    def verify(self, request: ConnectorRequest) -> VerificationResult: ...
