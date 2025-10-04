"""Package metadata for elaborlog.

Expose a single source of truth for the version. Prefer reading from
importlib.metadata so that an editable install or wheel always reports
the version declared in pyproject.toml. Fallback to a hardcoded string
to avoid import errors when metadata is unavailable (e.g. during some
packaging edge cases or direct source usage without installation).
"""

from __future__ import annotations

from importlib import metadata as _metadata

__all__ = ["__version__"]

_FALLBACK_VERSION = "0.2.1"  # MUST match pyproject.toml [project].version

try:  # pragma: no cover - success path covered indirectly via CLI test
	__version__ = _metadata.version("elaborlog")  # type: ignore[assignment]
except Exception:  # pragma: no cover - fallback exercised if metadata missing
	__version__ = _FALLBACK_VERSION

