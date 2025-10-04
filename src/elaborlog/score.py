import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple, Optional

from .config import LEVEL_BONUS, ScoringConfig
from .templates import to_template
from .tokenize import tokens


@dataclass
class LineScore:
    score: float
    token_info: float
    template_info: float
    level_bonus: float
    novelty: float
    tpl: str
    toks: List[str]


class InfoModel:
    """
    Online frequency model with Laplace smoothing and gentle exponential decay.
    Score = w_token * avg_token_self_info + w_template * template_self_info + w_level * bonus
    self_info(x) = -log2( p(x) ), with p estimated from counts.
    """

    def __init__(self, cfg: ScoringConfig | None = None) -> None:
        self.cfg = cfg or ScoringConfig()
        self.token_counts: Dict[str, float] = {}
        self.template_counts: Dict[str, float] = {}
        # Store unscaled counts; effective counts = stored * g
        self.total_tokens: float = 0.0  # unscaled aggregate
        self.total_templates: float = 0.0
        self._seen_lines = 0
        # Lazy decay parameters
        self.g: float = 1.0  # global scale factor
        self.decay_alpha: float = 1.0 - self.cfg.decay  # original cfg.decay ~= per-line multiplier; alpha = 1-decay
        self.decay_every: int = max(1, self.cfg.decay_every)
        self._last_decay_line: int = 0
        # Guardrail counters
        self.lines_truncated: int = 0
        self.lines_token_truncated: int = 0
        self.lines_dropped: int = 0

    def _prob(self, count: float, total: float, vocab: int) -> float:
        # Apply global scale factor lazily.
        eff_count = count * self.g
        eff_total = total * self.g
        return (eff_count + self.cfg.alpha) / (eff_total + self.cfg.alpha * max(1, vocab))

    @staticmethod
    def _self_info(prob: float) -> float:
        return -math.log2(max(prob, 1e-12))

    def _decay_maybe(self) -> None:
        """Apply lazy decay by updating global scale factor only."""
        if self._seen_lines == 0:
            return
        if self._seen_lines - self._last_decay_line >= self.decay_every:
            # Effective per-line decay multiplier in cfg.decay; number of decays elapsed:
            steps = (self._seen_lines - self._last_decay_line) // self.decay_every
            if steps > 0:
                # Multiply global scale g by decay**steps
                self.g *= self.cfg.decay ** steps
                self._last_decay_line += steps * self.decay_every

    def _prune_tokens(self) -> None:
        max_tokens = self.cfg.max_tokens
        if max_tokens <= 0:
            return
        while len(self.token_counts) > max_tokens:
            victim = min(self.token_counts, key=self.token_counts.get)
            removed = self.token_counts.pop(victim)
            self.total_tokens = max(0.0, self.total_tokens - removed)

    def _prune_templates(self) -> None:
        max_templates = self.cfg.max_templates
        if max_templates <= 0:
            return
        while len(self.template_counts) > max_templates:
            victim = min(self.template_counts, key=self.template_counts.get)
            removed = self.template_counts.pop(victim)
            self.total_templates = max(0.0, self.total_templates - removed)

    def observe(self, line: str) -> None:
        # Guardrails: truncate very long raw lines
        if len(line) > self.cfg.max_line_length:
            line = line[: self.cfg.max_line_length]
            self.lines_truncated += 1
        # Update counts (unsupervised)
        tpl = to_template(line)
        toks = tokens(line, include_bigrams=self.cfg.include_bigrams)
        if len(toks) > self.cfg.max_tokens_per_line:
            # Keep only first N tokens; drop remainder
            toks = toks[: self.cfg.max_tokens_per_line]
            self.lines_token_truncated += 1
        if not toks:
            self._seen_lines += 1
            self._decay_maybe()
            return
        # Optional: drop lines that exceed both limits originally (already truncated above, so detect pre-state via counters?)
        # If both truncations happened (long and many tokens), treat as drop: do not update counts
        # Heuristic: if we truncated chars AND token truncation triggered in same observe, consider drop
        # (Simpler: if original line length > max_line_length and original tokenization would exceed cap.)
        # We approximate by: if line was truncated this call and lines_token_truncated incremented.
        # We can't easily know if both occurred without extra state; add a lightweight flag.
        # For minimalism, we skip drop; dropping would lose novelty cues. Comment left for potential future logic.

        inv_g = 1.0 / self.g  # add scaled so effective increment is 1 after multiplying by g
        for tok in toks:
            self.token_counts[tok] = self.token_counts.get(tok, 0.0) + inv_g
            self.total_tokens += inv_g

        self.template_counts[tpl] = self.template_counts.get(tpl, 0.0) + inv_g
        self.total_templates += inv_g
        if len(self.template_counts) > self.cfg.max_templates:
            self._prune_templates()
        if len(self.token_counts) > self.cfg.max_tokens:
            self._prune_tokens()

        self._seen_lines += 1
        self._decay_maybe()

    def score(self, line: str, level: Optional[str] = None) -> LineScore:
        tpl = to_template(line)
        toks = tokens(line, include_bigrams=self.cfg.include_bigrams)
        if not toks:
            return LineScore(0.0, 0.0, 0.0, 0.0, 0.0, tpl, toks)

        # Token self-information (average)
        vocab = len(self.token_counts)
        token_info_total = 0.0
        for tok in toks:
            count = self.token_counts.get(tok, 0.0)
            prob = self._prob(count, self.total_tokens, vocab)
            token_info_total += self._self_info(prob)
        token_info = token_info_total / max(1, len(toks))

        # Template self-information
        tvocab = len(self.template_counts)
        tpl_count = self.template_counts.get(tpl, 0.0)
        tpl_prob = self._prob(tpl_count, self.total_templates, tvocab)
        template_info = self._self_info(tpl_prob)

        # Severity bonus (small)
        level_bonus = LEVEL_BONUS.get((level or "").upper(), 0.0)

        novelty = 1.0 - math.exp(-token_info)
        score_value = (
            self.cfg.w_token * token_info
            + self.cfg.w_template * template_info
            + self.cfg.w_level * level_bonus
        )
        return LineScore(score_value, token_info, template_info, level_bonus, novelty, tpl, toks)

    def token_surprisals(self, toks: List[str]) -> List[Tuple[str, float, float, int]]:
        """Return (token, probability, surprisal bits, frequency in line)."""
        vocab = len(self.token_counts)
        counts = Counter(toks)
        details = []
        for tok, freq in counts.items():
            count = self.token_counts.get(tok, 0.0)
            prob = self._prob(count, self.total_tokens, vocab)
            details.append((tok, prob, self._self_info(prob), freq))
        details.sort(key=lambda item: (-item[2], item[0]))
        return details

    def template_probability(self, tpl: str) -> float:
        """Return probability estimate for a template."""
        tvocab = len(self.template_counts)
        tpl_count = self.template_counts.get(tpl, 0.0)
        return self._prob(tpl_count, self.total_templates, tvocab)

    # Persistence helpers -------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serialisable snapshot of the current model state."""
        return {
            "version": 3,
            "cfg": asdict(self.cfg),
            "token_counts": self.token_counts,
            "template_counts": self.template_counts,
            "total_tokens": self.total_tokens,
            "total_templates": self.total_templates,
            "seen_lines": self._seen_lines,
            "g": self.g,
            "last_decay_line": self._last_decay_line,
            "lines_truncated": self.lines_truncated,
            "lines_token_truncated": self.lines_token_truncated,
            "lines_dropped": self.lines_dropped,
        }

    def _apply_snapshot(self, snap: Mapping[str, Any]) -> None:
        self.token_counts = {str(k): float(v) for k, v in snap.get("token_counts", {}).items()}
        self.template_counts = {str(k): float(v) for k, v in snap.get("template_counts", {}).items()}
        self.total_tokens = float(snap.get("total_tokens", 0.0))
        self.total_templates = float(snap.get("total_templates", 0.0))
        self._seen_lines = int(snap.get("seen_lines", 0))
        self.g = float(snap.get("g", 1.0))
        self._last_decay_line = int(snap.get("last_decay_line", 0))
        self.lines_truncated = int(snap.get("lines_truncated", 0))
        self.lines_token_truncated = int(snap.get("lines_token_truncated", 0))
        self.lines_dropped = int(snap.get("lines_dropped", 0))

    def save(self, path: str | Path) -> Path:
        """Persist current state to disk as JSON."""
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        with path_obj.open("w", encoding="utf-8") as handle:
            json.dump(self.snapshot(), handle, indent=2)
        return path_obj

    @classmethod
    def from_snapshot(
        cls,
        snap: Mapping[str, Any],
        cfg_override: ScoringConfig | None = None,
    ) -> "InfoModel":
        cfg_data = snap.get("cfg") or {}
        base_cfg = ScoringConfig(**cfg_data)
        if cfg_override is not None:
            for field in cfg_override.__dataclass_fields__:
                setattr(base_cfg, field, getattr(cfg_override, field))
        model = cls(base_cfg)
        model._apply_snapshot(snap)
        return model

    @classmethod
    def load(cls, path: str | Path, cfg_override: ScoringConfig | None = None) -> "InfoModel":
        """Load model state from disk."""
        path_obj = Path(path)
        with path_obj.open("r", encoding="utf-8") as handle:
            snap = json.load(handle)
        return cls.from_snapshot(snap, cfg_override=cfg_override)
