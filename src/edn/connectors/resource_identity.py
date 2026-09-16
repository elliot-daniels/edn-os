"""Exact provider identities mapped into EDN's durable authority namespace.

Mapping is not an authorization grant. Hosts must approve the resulting ID;
connectors still bind that authority to the exact configured provider resource.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from edn.core.security import validate_identifier


@dataclass(frozen=True, slots=True)
class ProviderResourceIdentity:
    provider: str
    tenant_id: str
    account_id: str
    resource_kind: str
    provider_id: str

    def __post_init__(self) -> None:
        for value in self._parts():
            if (
                not isinstance(value, str)
                or not value.strip()
                or any(ord(char) < 32 or ord(char) == 127 for char in value)
            ):
                raise ValueError("provider identity requires exact nonblank text")
        validate_identifier(self.provider, "provider")
        validate_identifier(self.resource_kind, "resource_kind")

    def _parts(self) -> tuple[str, ...]:
        return (
            self.provider,
            self.tenant_id,
            self.account_id,
            self.resource_kind,
            self.provider_id,
        )

    @property
    def authority_id(self) -> str:
        # Versioned, unambiguous framing; no trimming, case folding, decoding,
        # truncation or process-random hash. Full SHA-256 is collision-resistant.
        encoded = json.dumps(
            self._parts(), ensure_ascii=True, separators=(",", ":")
        ).encode("ascii")
        return "provider-v1:" + hashlib.sha256(encoded).hexdigest()
