"""File logging, so a failed dictation leaves evidence behind."""
from __future__ import annotations

import logging
from pathlib import Path

from .config import config_dir

MAX_BYTES = 1_000_000


def log_path() -> Path:
    return config_dir() / "yanzvoice.log"


def setup() -> logging.Logger:
    path = log_path()
    # Cheap rotation: a single truncate beats pulling in a handler dependency.
    try:
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.unlink()
    except OSError:
        pass

    logger = logging.getLogger("yanzvoice")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%Y-%m-%d %H:%M:%S")
    try:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    except OSError:
        pass

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    return logger


log = setup()
