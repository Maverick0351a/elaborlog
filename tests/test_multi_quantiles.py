import math
from elaborlog.score import InfoModel
from elaborlog.config import ScoringConfig
from elaborlog.quantiles import P2Quantile

# Reuse synthetic stream pattern similar to single quantile tests but shorter.

def synthetic_stream(n: int = 6000):
    for i in range(n):
        if i % 400 == 0:
            yield f"CRITICAL: failure code={i}", "CRITICAL"
        elif i % 90 == 0:
            yield f"ERROR: glitch id={i}", "ERROR"
        else:
            yield f"INFO: ok seq={i}", "INFO"


def test_multiple_p2_estimators_progress():
    cfg = ScoringConfig()
    model = InfoModel(cfg)
    qs = [0.99, 0.995]
    p2s = [P2Quantile(q=q) for q in qs]
    burn_in = 500
    counts = {q: 0 for q in qs}
    evaluated = 0

    for idx, (line, level) in enumerate(synthetic_stream(5000), start=1):
        model.observe(line)
        sc = model.score(line, level=level)
        for est in p2s:
            est.update(sc.novelty)
        if idx <= burn_in or idx < 50:
            continue
        evaluated += 1
        for est in p2s:
            if sc.novelty >= est.value():
                counts[est.q] += 1

    # Each observed rate should roughly approximate (1 - q) within a loose tolerance.
    for q in qs:
        observed = counts[q] / max(1, evaluated)
        expected = 1 - q
        assert observed > 0, "No alerts triggered for quantile"
        assert math.isclose(observed, expected, rel_tol=0.8, abs_tol=0.02)


def test_estimator_ordering():
    # Higher quantile should yield threshold >= lower quantile after enough samples.
    cfg = ScoringConfig()
    model = InfoModel(cfg)
    p_low = P2Quantile(q=0.99)
    p_high = P2Quantile(q=0.995)
    for idx, (line, level) in enumerate(synthetic_stream(4000), start=1):
        model.observe(line)
        sc = model.score(line, level=level)
        p_low.update(sc.novelty)
        p_high.update(sc.novelty)
    assert p_high.value() >= p_low.value() - 1e-6
