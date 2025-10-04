import re
from typing import List, Tuple

# Precompiled patterns and replacement tokens in a fixed order (order matters for specificity)
_REPLACERS: List[Tuple[re.Pattern[str], str]] = [
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


def to_template(line: str) -> str:
    x = line
    for pattern, repl in _REPLACERS:
        x = pattern.sub(repl, x)
    return " ".join(x.split())
