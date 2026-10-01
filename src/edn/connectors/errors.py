"""Machine-readable connector failures with content-safe explanations."""

from __future__ import annotations

from typing import ClassVar


class ConnectorError(Exception):
    code: ClassVar[str] = "connector_error"
    transient: ClassVar[bool] = False

    def __init__(self, explanation: str, *, connector_id: str | None = None) -> None:
        if not explanation.strip() or any(char in explanation for char in "\r\n"):
            raise ValueError(
                "connector error explanation must be nonblank and single-line"
            )
        if len(explanation) > 512:
            raise ValueError("connector error explanation is too long")
        self.explanation = explanation
        self.connector_id = connector_id
        super().__init__(explanation)

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "code": self.code,
            "explanation": self.explanation,
            "connector_id": self.connector_id,
            "transient": self.transient,
        }


class ConfigurationError(ConnectorError):
    code = "configuration_error"


class AuthenticationRequiredError(ConnectorError):
    code = "authentication_required"


class PermissionDeniedError(ConnectorError):
    code = "permission_denied"


class ApprovalRequiredError(ConnectorError):
    code = "approval_required"


class DependencyMissingError(ConnectorError):
    code = "dependency_missing"


class SourceUnavailableError(ConnectorError):
    code = "source_unavailable"


class UnsupportedOperationError(ConnectorError):
    code = "unsupported_operation"


class TransientConnectorError(ConnectorError):
    code = "transient_failure"
    transient = True


class InvalidCheckpointError(ConnectorError):
    code = "invalid_checkpoint"


class IncompatibleSourceStateError(ConnectorError):
    code = "incompatible_source_state"


class VerificationFailureError(ConnectorError):
    code = "verification_failure"


class IndeterminateSafetyError(ConnectorError):
    code = "indeterminate_safety_state"
