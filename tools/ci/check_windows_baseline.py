"""Reject Windows failure drift; preserves Linux's zero-failure gate."""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
expected = json.loads((ROOT / "config/ci/windows-baseline.json").read_text())
known = {entry["id"]: entry for entry in expected["known_failures"]}
known_skips = set(expected["known_skips"])
cases = list(ET.parse(sys.argv[1]).iter("testcase"))
observed = set()
errors = []
if len(cases) < expected["expected_total_tests"]:
    errors.append("Test collection shrank below baseline")
seen = set()
for case in cases:
    identity = case.get("classname", "") + "::" + case.get("name", "")
    seen.add(identity)
    failure = case.find("failure")
    error = case.find("error")
    skip = case.find("skipped")
    if error is not None:
        errors.append("Test/setup error: " + identity)
    if failure is not None:
        observed.add(identity)
        record = known.get(identity)
        text = failure.text or ""
        alternate = record.get("alternate_signature") if record else None
        # The one evidenced runner alternative must be the terminal exception,
        # not a substring in source/context for an unrelated assertion failure.
        matches_alternate = (
            isinstance(alternate, str)
            and (failure.get("message") or "").startswith(alternate)
            and alternate in text
        )
        if record is None or (
            record["required_signature"] not in text and not matches_alternate
        ):
            errors.append("New or changed failure: " + identity)
    if skip is not None and identity not in known_skips:
        errors.append("New skip: " + identity)
missing = (known.keys() | known_skips) - seen
errors.extend("Baseline test missing: " + identity for identity in sorted(missing))
if errors:
    raise SystemExit("\n".join(errors))
print(
    f"Baseline guard passed: {len(observed)} known failures; "
    f"{len(known.keys() - observed)} baseline failures now passing"
)
