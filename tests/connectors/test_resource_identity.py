import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from edn.connectors.resource_identity import ProviderResourceIdentity
from edn.core.security import validate_identifier

OPAQUE = "AQMk" + "Ab0_-" * 40 + "+/=%?#雪=="


def identity(native=OPAQUE, **changes):
    return replace(
        ProviderResourceIdentity(
            "microsoft-graph", "tenant", "owner@example.com", "calendar", native
        ),
        **changes,
    )


def test_mapping_is_stable_exact_and_namespaced():
    value = identity()
    validate_identifier(value.authority_id, "authority")
    assert value.provider_id == OPAQUE
    assert ProviderResourceIdentity(**asdict(value)) == value
    assert ProviderResourceIdentity(**asdict(value)).authority_id == value.authority_id
    variants = [
        identity(OPAQUE + "x"),
        identity(OPAQUE.lower()),
        identity(tenant_id="other"),
        identity(account_id="other"),
        identity(resource_kind="folder"),
        identity(provider="other"),
    ]
    assert len({value.authority_id, *(v.authority_id for v in variants)}) == 7
    with pytest.raises(ValueError):
        validate_identifier(OPAQUE, "still-invalid-in-core")


@pytest.mark.parametrize(
    "field", ["provider", "tenant_id", "account_id", "resource_kind", "provider_id"]
)
@pytest.mark.parametrize("bad", ["", " ", "\n", "x\x00y", None])
def test_incomplete_or_malformed_identity_fails_closed(field, bad):
    with pytest.raises(ValueError):
        identity(**{field: bad})


def test_mapping_survives_a_new_process():
    code = (
        "import json,sys; from edn.connectors.resource_identity import "
        "ProviderResourceIdentity; "
        "print(ProviderResourceIdentity(**json.loads(sys.stdin.read())).authority_id)"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(asdict(identity())),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    assert result.stdout.strip() == identity().authority_id
