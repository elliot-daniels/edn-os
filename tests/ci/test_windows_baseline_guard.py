"""Offline CI guard regressions; no platform protection or source access bypass."""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASELINE = json.loads((ROOT / "config/ci/windows-baseline.json").read_text())
TARGET = (
    "tests.development.test_delegated_authority::test_symlink_path_attack_is_denied"
)
ALTERNATE = "AttributeError: module 'os' has no attribute 'geteuid'"


@pytest.fixture
def report():
    suite = ET.Element("testsuite")
    names = [entry["id"] for entry in BASELINE["known_failures"]]
    names.extend(BASELINE["known_skips"])
    for identity in names:
        classname, name = identity.split("::", 1)
        ET.SubElement(suite, "testcase", classname=classname, name=name)
    for index in range(BASELINE["expected_total_tests"] - len(names)):
        ET.SubElement(suite, "testcase", classname="synthetic.passing", name=str(index))
    return suite


def find_case(report, identity):
    classname, name = identity.split("::", 1)
    return next(
        case
        for case in report
        if case.get("classname") == classname and case.get("name") == name
    )


def run_guard(tmp_path, report):
    path = tmp_path / "junit.xml"
    ET.ElementTree(report).write(path, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ROOT / "tools/ci/check_windows_baseline.py"), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "signature,accepted",
    [
        ("OSError: [WinError 1314] A required privilege is not held", True),
        (ALTERNATE, True),
        ("AttributeError: module 'os' has no attribute 'getuid'", False),
        ("AttributeError: module 'os' has no attribute 'geteuid_extra'", False),
        ("AssertionError: unsafe symlink accepted", False),
        ("PermissionError: [WinError 5] Access denied", False),
    ],
)
def test_only_evidenced_symlink_failures_accepted(
    tmp_path, report, signature, accepted
):
    ET.SubElement(
        find_case(report, TARGET), "failure", message=signature
    ).text = signature
    result = run_guard(tmp_path, report)
    assert (result.returncode == 0) is accepted


def test_alternate_cannot_mask_unrelated_terminal_exception(tmp_path, report):
    ET.SubElement(
        find_case(report, TARGET),
        "failure",
        message="AssertionError: protection regressed",
    ).text = ALTERNATE
    assert run_guard(tmp_path, report).returncode != 0


def test_alternate_does_not_apply_to_other_baseline_case(tmp_path, report):
    identity = next(
        entry["id"]
        for entry in BASELINE["known_failures"]
        if entry["category"] == "posix_root_assertion_on_windows"
    )
    ET.SubElement(
        find_case(report, identity), "failure", message=ALTERNATE
    ).text = ALTERNATE
    assert run_guard(tmp_path, report).returncode != 0


def test_new_failure_identity_still_rejected(tmp_path, report):
    case = next(case for case in report if case.get("classname") == "synthetic.passing")
    ET.SubElement(case, "failure", message=ALTERNATE).text = ALTERNATE
    assert run_guard(tmp_path, report).returncode != 0


@pytest.mark.parametrize("kind", ["error", "skipped"])
def test_new_setup_error_or_skip_still_rejected(tmp_path, report, kind):
    case = next(case for case in report if case.get("classname") == "synthetic.passing")
    ET.SubElement(case, kind).text = "Synthetic bypass"
    assert run_guard(tmp_path, report).returncode != 0


def test_collection_shrink_still_rejected(tmp_path, report):
    report.remove(report[-1])
    assert run_guard(tmp_path, report).returncode != 0


def test_missing_baseline_case_rejected_even_when_collection_size_unchanged(
    tmp_path, report
):
    report.remove(find_case(report, TARGET))
    ET.SubElement(report, "testcase", classname="synthetic.passing", name="replacement")
    assert run_guard(tmp_path, report).returncode != 0


def test_resolved_baseline_failures_remain_accepted(tmp_path, report):
    assert run_guard(tmp_path, report).returncode == 0
