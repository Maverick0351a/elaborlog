import re
from typing import List


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def tokens(text: str, include_bigrams: bool = False) -> List[str]:
    """Lowercase alphanumeric + underscore tokens with optional bigrams."""
    toks = _WORD_RE.findall(text.lower())
    if include_bigrams and len(toks) >= 2:
        toks = toks + [f"{toks[i]}__{toks[i + 1]}" for i in range(len(toks) - 1)]
    return toks
