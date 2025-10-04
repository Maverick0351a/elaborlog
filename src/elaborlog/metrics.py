"""Metrics helper for InfoModel.

Provides a lightweight, dependency-free snapshot of internal counters suitable
for exposure via HTTP or logging. Avoids mutating the model.
"""
from __future__ import annotations

from typing import Dict, Any

from .score import InfoModel


def model_metrics(model: InfoModel) -> Dict[str, Any]:
    return {
        "tokens": len(model.token_counts),
        "templates": len(model.template_counts),
        "total_tokens": model.total_tokens,
        "total_templates": model.total_templates,
        "seen_lines": model._seen_lines,
        "g": model.g,
        "renormalizations": model.renormalizations,
        "lines_truncated": model.lines_truncated,
        "lines_token_truncated": model.lines_token_truncated,
        "lines_dropped": model.lines_dropped,
        "config": {
            "decay": model.cfg.decay,
            "decay_every": model.cfg.decay_every,
            "max_tokens": model.cfg.max_tokens,
            "max_templates": model.cfg.max_templates,
            "max_tokens_per_line": model.cfg.max_tokens_per_line,
            "max_line_length": model.cfg.max_line_length,
            "include_bigrams": model.cfg.include_bigrams,
            "split_camel": model.cfg.split_camel,
            "split_dot": model.cfg.split_dot,
        },
    }

__all__ = ["model_metrics"]
