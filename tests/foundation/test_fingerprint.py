"""Tests for read-only file fingerprinting."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from edn.foundation.errors import PathValidationError, ValidationError
from edn.foundation.fingerprint import sha256_file

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def test_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.bin"
    target.write_bytes(b"")

    assert sha256_file(target) == _EMPTY_SHA256


def test_known_small_content(tmp_path: Path) -> None:
    target = tmp_path / "small.txt"
    content = b"edn-os foundation fingerprint"
    target.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()

    assert sha256_file(target) == expected


def test_multi_chunk_file(tmp_path: Path) -> None:
    target = tmp_path / "large.bin"
    content = b"x" * 5000
    target.write_bytes(content)
    chunk_size = 1024
    expected = hashlib.sha256(content).hexdigest()

    assert sha256_file(target, chunk_size=chunk_size) == expected


def test_custom_chunk_size(tmp_path: Path) -> None:
    target = tmp_path / "chunked.bin"
    content = b"abcdefgh" * 10
    target.write_bytes(content)

    assert sha256_file(target, chunk_size=3) == hashlib.sha256(content).hexdigest()
    assert sha256_file(target, chunk_size=64) == hashlib.sha256(content).hexdigest()


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PathValidationError, match="does not exist"):
        sha256_file(tmp_path / "missing.bin")


def test_directory_path_raises(tmp_path: Path) -> None:
    with pytest.raises(PathValidationError, match="not a regular file"):
        sha256_file(tmp_path)


@pytest.mark.parametrize("chunk_size", [0, -1, -1024])
def test_invalid_chunk_size_raises(tmp_path: Path, chunk_size: int) -> None:
    target = tmp_path / "file.bin"
    target.write_bytes(b"data")

    with pytest.raises(ValidationError, match="chunk_size"):
        sha256_file(target, chunk_size=chunk_size)


def test_source_file_unchanged_after_hashing(tmp_path: Path) -> None:
    target = tmp_path / "immutable.bin"
    content = b"unchanged-content"
    target.write_bytes(content)

    sha256_file(target)

    assert target.read_bytes() == content
