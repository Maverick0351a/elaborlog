import math
import random

import numpy as np
import pytest

from elaborlog.quantiles import P2Quantile


def test_p2_converges_on_normal():
    random.seed(0)
    q = 0.995
    est = P2Quantile(q=q)
    # Warm with 5 samples through update path
    for _ in range(100_000):
        x = random.gauss(0, 1)
        est.update(x)
    v = est.value()
    # True 99.5th for N(0,1) ~ 2.575
    assert not math.isnan(v)
    assert 2.47 <= v <= 2.67  # ±0.1 tolerance band


def test_p2_tracks_shift():
    random.seed(1)
    q = 0.99
    est = P2Quantile(q=q)
    # initial distribution N(0,1)
    for _ in range(10_000):
        est.update(random.gauss(0, 1))
    before = est.value()
    # shift mean to 2
    for _ in range(2_000):
        est.update(random.gauss(2, 1))
    after = est.value()
    # Expect noticeable increase; 99th of N(0,1) ~ 2.33, of N(2,1) ~ 4.33
    assert after - before > 1.0
    assert after > before


def test_p2_matches_percentile_on_batch():
    random.seed(2)
    q = 0.98
    est = P2Quantile(q=q)
    data = [random.random() ** 2 for _ in range(50_000)]  # skewed distribution
    for x in data:
        est.update(x)
    batch = np.percentile(data, q * 100.0)
    v = est.value()
    # Allow a small relative error
    assert v == pytest.approx(batch, rel=0.02, abs=0.01)
