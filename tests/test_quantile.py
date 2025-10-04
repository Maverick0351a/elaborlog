from collections import deque

from elaborlog.cli import compute_quantile
import pytest


def test_quantile_basic():
    d = deque([1.0, 2.0, 3.0, 4.0])
    # Median
    assert compute_quantile(d, 0.5) == 2.5
    # Min
    assert compute_quantile(d, 0.0) == 1.0
    # Max (just below 1 uses interpolation formula but should end at last element)
    assert compute_quantile(d, 0.999) == pytest.approx(4.0, rel=1e-3)


def test_quantile_singleton():
    d = deque([42.0])
    assert compute_quantile(d, 0.2) == 42.0


def test_quantile_empty():
    d = deque([])
    import math

    assert compute_quantile(d, 0.5) == math.inf
