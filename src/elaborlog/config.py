from dataclasses import dataclass


@dataclass
class ScoringConfig:
    # Laplace smoothing for token probabilities
    alpha: float = 1.0
    # Weighting for token-level info vs template rarity vs level/severity
    w_token: float = 1.0
    w_template: float = 1.0
    w_level: float = 0.25
    # Exponential decay for "recency" (applied periodically)
    decay: float = 0.9999
    # Window for nearest-neighbor context search
    nn_window: int = 5000
    nn_topk: int = 2
    # When streaming tailing, how often to apply decay (every N lines)
    decay_every: int = 1
    # Maximum vocabulary size before evicting least-used features
    max_tokens: int = 30000
    max_templates: int = 10000
    # Tokenization controls
    include_bigrams: bool = False
    split_camel: bool = False  # split mixedCase / PascalCase tokens into components
    split_dot: bool = False    # split dotted.identifiers.into parts while retaining original
    # Guardrails
    max_line_length: int = 2000  # characters; lines longer will be truncated
    max_tokens_per_line: int = 400  # tokens after tokenization (before bigrams)
    # Numerical stability: when lazy global scale factor g shrinks below this
    # threshold, renormalize by folding g into stored counts and resetting g=1.0.
    renorm_min_scale: float = 1e-9


# Simple severity map; tune as needed
LEVEL_BONUS = {
    "CRITICAL": 1.0,
    "ERROR": 0.7,
    "WARN": 0.3,
    "WARNING": 0.3,
    "INFO": 0.0,
    "DEBUG": -0.05,
    "TRACE": -0.1,
}
