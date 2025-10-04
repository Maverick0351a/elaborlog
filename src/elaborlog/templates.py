import re
import sys
from typing import Tuple  # List not needed with PEP 585 generics

# Precompiled patterns and replacement tokens in a fixed order (order matters for specificity)
_REPLACERS: list[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\b"), "<ts>"),
    (
        re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
        ),
        "<uuid>",
    ),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<ip>"),
    (re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"), "<email>"),
    (re.compile(r"\bhttps?://[^\s]+\b"), "<url>"),
    (
        re.compile(
            r"(?P<quote>['\"])?(?P<path>(?:/[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)+|[A-Za-z]:\\[A-Za-z0-9._\\-]+))(?(quote)(?P=quote))"
        ),
        "<path>",
    ),
    (re.compile(r"(['\"])(?:\\.|(?!\1).)*\1"), "<str>"),
    (re.compile(r"\b\d+\b"), "<num>"),
]

# --- Pluggable custom masks -------------------------------------------------
# Users can supply additional regex -> replacement rules at runtime via CLI.
# We keep them module-global so both scoring model and lightweight commands
# (like 'cluster') see the same behavior without needing to thread config
# everywhere. The CLI resets these per invocation (process scoped).
_CUSTOM_REPLACERS: list[Tuple[re.Pattern[str], str]] = []
_CUSTOM_ORDER: str = "before"  # 'before' (default) or 'after'


def set_custom_replacers(pairs: list[Tuple[re.Pattern[str], str]], order: str = "before") -> None:
    """Install custom replacers.

    Parameters
    ----------
    pairs: list of (compiled_regex, replacement)
        Replacement token strings should be short (e.g. <user>, <id>). They are
        applied verbatim; no further escaping.
    order: 'before' | 'after'
        Whether to apply custom masks before the built-in canonicalization
        rules (default) or after.
    """
    global _CUSTOM_REPLACERS, _CUSTOM_ORDER
    _CUSTOM_REPLACERS = pairs
    _CUSTOM_ORDER = order if order in {"before", "after"} else "before"


def clear_custom_replacers() -> None:
    """Reset to no custom masks (mainly for tests)."""
    global _CUSTOM_REPLACERS, _CUSTOM_ORDER
    _CUSTOM_REPLACERS = []
    _CUSTOM_ORDER = "before"


def _apply(replacers: list[Tuple[re.Pattern[str], str]], text: str) -> str:
    for pattern, repl in replacers:
        try:
            text = pattern.sub(repl, text)
        except Exception as exc:  # pragma: no cover - defensive; regex failures rare
            print(f"[elaborlog] warning: custom replacer failed: {exc}", file=sys.stderr)
    return text


def to_template(line: str) -> str:
    """Return canonical template for a raw log line.

    Custom masks (user supplied) run before or after the built-ins depending
    on configured order. Order can matter for overlapping patterns (e.g. a
    custom mask targeting digits vs the built-in <num> substitute)."""
    x = line
    if _CUSTOM_REPLACERS and _CUSTOM_ORDER == "before":
        x = _apply(_CUSTOM_REPLACERS, x)
    x = _apply(_REPLACERS, x)
    if _CUSTOM_REPLACERS and _CUSTOM_ORDER == "after":
        x = _apply(_CUSTOM_REPLACERS, x)
    return " ".join(x.split())
