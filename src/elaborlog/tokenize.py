import re


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")

_CAMEL_SPLIT_RE = re.compile(
    r"(?<!^)(?:(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z]))"
)


def _split_camel(token: str) -> list[str]:
    parts = _CAMEL_SPLIT_RE.split(token)
    if len(parts) <= 1:
        return [token]
    return [p for p in parts if p]


def _augment_with_splits(base_tokens: list[str], split_camel: bool, split_dot: bool) -> list[str]:
    if not split_camel and not split_dot:
        return base_tokens
    augmented: list[str] = []
    for tok in base_tokens:
        augmented.append(tok)
        # Dot splitting first (retain original always)
        pieces = [tok]
        if split_dot and "." in tok and tok.count(".") < 10:  # guard runaway
            dot_parts = [p for p in tok.split(".") if p]
            if len(dot_parts) > 1:
                pieces = dot_parts
        # Camel splitting on each piece (recursively but shallow)
        final_parts: list[str] = []
        for p in pieces:
            if split_camel and len(p) <= 80:  # avoid pathological huge tokens
                final_parts.extend(_split_camel(p))
            else:
                final_parts.append(p)
        # Avoid re-adding token identical to original only set if any change
        if any(fp != tok for fp in final_parts):
            augmented.extend(final_parts)
    return augmented


def tokens(
    text: str,
    include_bigrams: bool = False,
    split_camel: bool = False,
    split_dot: bool = False,
) -> list[str]:
    """Tokenize a string with optional camelCase and dotted segmentation.

    Design choices:
    - Base tokens are alnum/underscore words (legacy behavior) for stability.
    - For splitting features we re-scan the raw text for candidate dotted / camel fragments.
    - We retain the raw dotted token if split_dot is enabled (e.g., alpha.beta.gamma) and also add parts.
    - For camel splitting we retain original lowercased token and add components when they differ.
    - Deduplicate while preserving insertion order.
    """
    lowered = text.lower()
    base = _WORD_RE.findall(lowered)
    out: list[str] = []
    seen = set()

    def _add(tok: str) -> None:
        if not tok:
            return
        if tok not in seen:
            seen.add(tok)
            out.append(tok)

    # Start with base tokens in order
    for b in base:
        _add(b)

    if split_dot and "." in text:
        # Extract dotted sequences containing letters/numbers and dots
        for match in re.finditer(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", text):
            raw = match.group(0).lower()
            _add(raw)
            parts = [p for p in raw.split('.') if p]
            if len(parts) > 1:
                for p in parts:
                    _add(p)

    if split_camel:
        # Scan original text preserving case; then split and lowercase parts.
        for match in re.finditer(r"[A-Za-z][A-Za-z0-9]+", text):
            raw = match.group(0)
            if raw.islower() or raw.isupper() or len(raw) < 4:
                continue
            subs = _split_camel(raw)
            if len(subs) > 1:
                for s in subs:
                    _add(s.lower())

    if include_bigrams:
        if len(base) >= 2:
            for i in range(len(base) - 1):
                _add(f"{base[i]}__{base[i+1]}")
    return out
