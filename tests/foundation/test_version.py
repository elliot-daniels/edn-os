"""Smoke tests for Foundation version metadata."""

import edn
from edn.foundation.version import __version__


def test_foundation_version() -> None:
    assert __version__ == "0.1.0"


def test_package_version_matches_foundation() -> None:
    assert edn.__version__ == __version__
