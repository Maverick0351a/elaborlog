from elaborlog.score import InfoModel
from elaborlog.config import ScoringConfig


def test_g_renormalization_preserves_probabilities():
    cfg = ScoringConfig(decay=0.90, decay_every=1, renorm_min_scale=1e-6)
    m = InfoModel(cfg)
    # Warm model
    for _ in range(50):
        m.observe("INFO alpha beta gamma")
    # Use internal probability helper for a stable token ("info")
    vocab = len(m.token_counts)
    p_before = m._prob(m.token_counts.get("info", 0.0), m.total_tokens, vocab)
    # Force renormalization
    for _ in range(10000):
        m.observe("INFO alpha delta epsilon")
        if m.renormalizations > 0:
            break
    assert m.renormalizations >= 1
    vocab_after = len(m.token_counts)
    p_after = m._prob(m.token_counts.get("info", 0.0), m.total_tokens, vocab_after)
    # Compute effective count ratio pre/post renorm; should be ~1 allowing small drift.
    # Accept greater drift due to growth of vocab from new tokens (delta, epsilon) influencing smoothing term.
    assert abs(p_before - p_after) / p_before < 0.06  # <6% relative drift
