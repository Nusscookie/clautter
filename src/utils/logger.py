"""Logging setup for AI Editor Assistant."""

from __future__ import annotations
import logging
import logging.handlers
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with rotating file + console handlers."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_dir = Path.home() / ".clutter" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    fh = logging.handlers.RotatingFileHandler(
        log_dir / "ai_editor.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger
