"""Tests for Foundation logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from edn.foundation.logging import configure_logging, get_logger


def test_log_directory_created_only_on_configuration(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    assert not log_root.exists()

    configure_logging(log_root)

    assert log_root.is_dir()


def test_log_file_created_with_expected_format(tmp_path: Path) -> None:
    log_root = tmp_path / "logs"
    configure_logging(log_root, level=logging.DEBUG)
    logger = get_logger("foundation.test")
    logger.info("import started")

    log_file = log_root / "edn-os.log"
    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert "INFO [edn.foundation.test] import started" in content
    assert "T" in content.split()[0]  # ISO-style date component


def test_console_handler_present(tmp_path: Path) -> None:
    configure_logging(tmp_path / "logs")
    root_logger = logging.getLogger("edn")
    handler_types = {type(handler) for handler in root_logger.handlers}
    assert logging.StreamHandler in handler_types
    assert RotatingFileHandler in handler_types


def test_repeated_configuration_does_not_duplicate_handlers(
    tmp_path: Path,
) -> None:
    log_root = tmp_path / "logs"
    configure_logging(log_root)
    configure_logging(log_root)

    root_logger = logging.getLogger("edn")
    assert len(root_logger.handlers) == 2


def test_get_logger_returns_named_logger(tmp_path: Path) -> None:
    configure_logging(tmp_path / "logs")
    logger = get_logger("memory.import")

    assert logger.name == "edn.memory.import"


def test_get_logger_prefixes_non_edn_names(tmp_path: Path) -> None:
    configure_logging(tmp_path / "logs")
    logger = get_logger("custom.module")

    assert logger.name == "edn.custom.module"
