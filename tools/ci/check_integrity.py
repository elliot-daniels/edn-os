"""Offline JSON and frozen maker-source integrity checks; no service access."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for path in sorted((ROOT / "config").rglob("*.json")):
    json.loads(path.read_text(encoding="utf-8"))
for path in sorted((ROOT / "config").rglob("*.jsonl")):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            json.loads(line)
sidecar = ROOT / "config/work-capture-v1-activation-manifest.sha256"
expected = sidecar.read_text(encoding="utf-8").split()[0]
manifest = ROOT / "config/work-capture-v1-activation-manifest.json"
if hashlib.sha256(manifest.read_bytes()).hexdigest() != expected:
    raise SystemExit("Frozen activation manifest mismatch")
baseline = json.loads(
    (ROOT / "config/work-capture-power-app-baseline.json").read_text(encoding="utf-8")
)
controlled = baseline["source_control"]
source = (ROOT / controlled["root"]).resolve()
if not source.is_relative_to(ROOT) or not controlled["files"]:
    raise SystemExit("Unsafe or empty frozen source list")
for name, digest in controlled["files"].items():
    path = (source / name).resolve()
    if not path.is_relative_to(source):
        raise SystemExit("Unsafe frozen source path")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit("Frozen maker source mismatch")
print("JSON/JSONL and frozen activation/maker integrity passed")
