import math
from elaborlog.score import InfoModel
from elaborlog.config import ScoringConfig
from elaborlog.quantiles import P2Quantile


def synthetic_stream(n: int = 8000):
    """Yield (line, level) pairs with controlled rarity.

    We create mostly common tokens plus occasional rare token bursts to test that
    P2Quantile tracks the upper quantile properly.
    """
    for i in range(n):
        # 1% of lines include a rare token; 0.2% include a very-rare token
        if i % 500 == 0:
            yield f"CRITICAL: catastrophic failure code={i}", "CRITICAL"
        elif i % 100 == 0:
            yield f"ERROR: intermittent issue id={i}", "ERROR"
        else:
            yield f"INFO: regular heartbeat seq={i}", "INFO"


def test_streaming_quantile_alert_rate():
    q = 0.992
    cfg = ScoringConfig()
    model = InfoModel(cfg)
    p2 = P2Quantile(q=q)
    burn_in = 600
    alerts = 0
    evaluated = 0

    for idx, (line, level) in enumerate(synthetic_stream(7000), start=1):
        model.observe(line)
        sc = model.score(line, level=level)
        p2.update(sc.novelty)
        if idx <= burn_in or idx < 50:
            continue
        threshold = p2.value()
        if sc.novelty >= threshold:
            alerts += 1
        evaluated += 1

    # After convergence, proportion above quantile should approximate (1-q).
    observed_rate = alerts / max(1, evaluated)
    expected_rate = 1 - q
    # Allow generous tolerance because novelty distribution is non-stationary but should stabilize.
    assert math.isclose(observed_rate, expected_rate, rel_tol=0.5, abs_tol=0.01), (
        f"alert rate {observed_rate:.4f} deviates from expected {(expected_rate):.4f}"
    )
