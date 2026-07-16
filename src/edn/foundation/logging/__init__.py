"""Common logging configuration for EDN OS.

Modules request loggers via :func:`get_logger`. They must not configure
logging independently.

Sensitive-data policy
---------------------
Logging APIs accept **operational summaries only**. Callers must never pass:

- email or message bodies;
- attachment contents;
- tokens, passwords, or other secrets;
- full configuration file contents.

Module 000 does not automatically detect or redact sensitive text. Callers
are responsible for what they log.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
_LOG_FILENAME = "edn-os.log"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


def configure_logging(log_root: Path, level: int = logging.INFO) -> None:
    """Configure platform logging to file and console.

    Creates ``log_root`` only when this function is called explicitly.
    Repeated calls replace existing handlers without duplication.
    """
    log_root.mkdir(parents=True, exist_ok=True)
    log_file = log_root / _LOG_FILENAME

    root_logger = logging.getLogger("edn")
    root_logger.setLevel(level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    root_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a named logger under the ``edn`` hierarchy."""
    if not name.startswith("edn"):
        name = f"edn.{name}"
    return logging.getLogger(name)
