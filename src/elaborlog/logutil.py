"""Project-wide logging utilities.

Provides a single logger configured lazily; libraries embedding elaborlog can
override handlers or levels as needed. We default to WARNING to stay quiet
unless something noteworthy happens (e.g., regex failure, JSON parse error).
"""
from __future__ import annotations

import logging
from typing import Optional

_LOGGER: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        logger = logging.getLogger("elaborlog")
        # Only add a handler if the application hasn't configured logging.
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        _LOGGER = logger
    return _LOGGER

__all__ = ["get_logger"]
