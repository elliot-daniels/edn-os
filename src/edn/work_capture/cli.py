"""Synthetic/local Work Capture contract demonstration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from edn.work_capture.models import CaptureDraft, ProjectDefaults
from edn.work_capture.service import compile_capture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and plan a work capture")
    parser.add_argument("input", type=Path, help="Synthetic JSON capture envelope")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    value = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("capture envelope must be an object")
    defaults_value = _object(value.get("project_defaults"), "project_defaults")
    draft_value = _object(value.get("draft"), "draft")
    plan = compile_capture(
        CaptureDraft.from_dict(draft_value),
        ProjectDefaults.from_dict(defaults_value),
    )
    print(plan.to_json())
    return 0


def _object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
