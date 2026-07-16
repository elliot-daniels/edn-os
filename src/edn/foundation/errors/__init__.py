"""Platform-wide exception types.

Defines the shared error hierarchy. Domain-specific errors remain in
feature modules such as ``edn.memory``.
"""


class EDNError(Exception):
    """Base exception for EDN OS platform errors."""


class ConfigurationError(EDNError):
    """Raised when configuration cannot be loaded or is invalid."""


class ConfigurationFileNotFoundError(ConfigurationError):
    """Raised when the configuration file does not exist."""


class ConfigurationValidationError(ConfigurationError):
    """Raised when configuration content fails validation."""


class ValidationError(EDNError):
    """Raised when a function argument or input value fails validation."""


class PathValidationError(EDNError):
    """Raised when a runtime path violates the approved data-root policy."""


__all__ = [
    "ConfigurationError",
    "ConfigurationFileNotFoundError",
    "ConfigurationValidationError",
    "EDNError",
    "PathValidationError",
    "ValidationError",
]
