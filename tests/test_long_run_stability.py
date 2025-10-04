import math

from elaborlog.score import InfoModel
from elaborlog.config import ScoringConfig


def test_long_run_numeric_stability():
    # Configure aggressive decay so renormalization is triggered
    cfg = ScoringConfig()
    cfg.decay = 0.999  # slightly stronger decay
    cfg.decay_every = 1
    cfg.renorm_min_scale = 1e-6  # force earlier renorms
    cfg.max_tokens = 5000
    cfg.max_templates = 2000
    model = InfoModel(cfg)

    # Generate many synthetic lines with moderate diversity
    def make_line(kind: int, i: int) -> str:
        if kind == 0:
            return f"INFO user login success user={i}"
        if kind == 1:
            return f"WARN db connection slow latency={i}ms host=db{ i % 3 }"
        if kind == 2:
            return f"ERROR payment declined code={ i % 503 } user={ i % 997 } amount={ i % 17 }"
        return f"INFO cache lookup key=abcd{ i % 1000 }"
    total = 50_000
    for i in range(total):
        line = make_line(i % 4, i)
        model.observe(line)
        # Periodically score to exercise probability path
        if i % 2500 == 0:
            _ = model.score(line)

    # Basic invariants
    assert model.total_tokens > 0
    assert model.total_templates > 0
    assert model.g <= 1.0  # global scale never grows
    # Renormalization should have happened at least once with aggressive settings
    assert model.renormalizations >= 1
    # Probabilities remain normalized-ish: sample a few tokens and ensure p in (0,1]
    sample_tokens = list(model.token_counts.keys())[:50]
    for tok in sample_tokens:
        p = model._prob(model.token_counts[tok], model.total_tokens, len(model.token_counts))
        assert 0 < p <= 1.0
    # Novelty range check
    sc = model.score("ERROR payment declined code=402 user=9912 amount=10")
    assert 0.0 <= sc.novelty < 1.0
    # Vocab caps respected
    assert len(model.token_counts) <= cfg.max_tokens
    assert len(model.template_counts) <= cfg.max_templates
