import math
import random
from elaborlog.quantiles import P2Quantile


def test_p2_less_than_five_samples_exact():
    q = P2Quantile(0.9)
    samples = [5.0, 1.0, 3.0, 9.0]
    for s in samples:
        q.update(s)
    # With <5 samples, falls back to interpolation on sorted data
    sorted_vals = sorted(samples)
    # Manual interpolation for 0.9 over len=4 => idx=0.9*(3)=2.7 => between indices 2 and 3
    idx = 0.9 * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(len(sorted_vals) - 1, lo + 1)
    frac = idx - lo
    expected = sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac
    assert math.isclose(q.value(), expected, rel_tol=1e-9)


def test_p2_exact_after_five_initialization():
    # After exactly 5 samples, the median (q=0.5) estimate should equal the middle element of sorted first 5
    q = P2Quantile(0.5)
    samples = [10, 2, 7, 4, 20]
    for s in samples:
        q.update(float(s))
    assert q.value() == sorted(samples)[2]


def test_p2_converges_on_uniform_distribution():
    random.seed(0)
    q = P2Quantile(0.95)
    for _ in range(10000):
        q.update(random.random())
    # For U(0,1), 95th percentile ~0.95, allow small tolerance
    assert 0.93 < q.value() < 0.97


def test_p2_constant_sequence():
    q = P2Quantile(0.9)
    for _ in range(200):
        q.update(42.0)
    assert q.value() == 42.0
