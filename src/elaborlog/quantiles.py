"""Streaming quantile estimation using the P² algorithm (Jain & Chlamtac, 1985).

This keeps 5 markers for a single target quantile q. Memory O(1), update O(1).
Suitable for high-percentile estimates (q >= ~0.9). For small sample sizes (<5) it
falls back to exact sample quantiles.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List


@dataclass
class P2Quantile:
    q: float  # target quantile in (0,1)
    _n: int = 0
    _initialized: bool = False
    _heights: List[float] | None = None  # marker heights h[0..4]
    _positions: List[int] | None = None  # marker positions n[0..4]
    _desired: List[float] | None = None  # desired marker positions n'[0..4]
    _incs: List[float] | None = None     # increments dn[0..4]
    _buffer: List[float] | None = None   # initial sample buffer

    def __post_init__(self) -> None:
        if not (0 < self.q < 1):  # pragma: no cover - guard
            raise ValueError("q must be in (0,1)")
        self._buffer = []

    def update(self, x: float) -> None:
        """Observe one sample."""
        if not self._initialized:
            self._buffer.append(x)
            if len(self._buffer) == 5:
                self._buffer.sort()
                self._heights = self._buffer[:]  # h0..h4
                self._positions = [1, 2, 3, 4, 5]
                q = self.q
                self._desired = [1, 1 + 2*q, 1 + 4*q, 3 + 2*q, 5]
                self._incs = [0.0, q/2, q, (1+q)/2, 1.0]
                self._initialized = True
            return

        # Increment total count
        self._n += 1
        h = self._heights  # type: ignore
        n = self._positions  # type: ignore
        nd = self._desired  # type: ignore
        dn = self._incs  # type: ignore

        # Find k: cell in which x falls and update boundary heights
        if x < h[0]:
            h[0] = x
            k = 0
        elif x >= h[4]:
            h[4] = x
            k = 3
        else:
            k = 0
            while k < 4 and x >= h[k+1]:
                k += 1
            # Now x between h[k] and h[k+1]
        for i in range(k+1, 5):
            n[i] += 1
        for i in range(5):
            nd[i] += dn[i]

        # Adjust heights of interior markers if necessary
        for i in range(1, 4):
            d = nd[i] - n[i]
            if (d >= 1 and n[i+1] - n[i] > 1) or (d <= -1 and n[i-1] - n[i] < -1):
                d_sign = 1 if d > 0 else -1
                # Parabolic prediction
                hp = self._parabolic(i, d_sign, h, n)
                if h[i-1] < hp < h[i+1]:
                    h[i] = hp
                else:
                    # Linear fallback
                    h[i] = self._linear(i, d_sign, h, n)
                n[i] += d_sign

    def value(self) -> float:
        """Return current quantile estimate (exact if not initialized)."""
        if not self._initialized:
            if not self._buffer:
                return float('nan')
            data = sorted(self._buffer)
            if len(data) == 1:
                return data[0]
            # simple interpolation
            idx = self.q * (len(data)-1)
            lo = int(idx)
            hi = min(len(data)-1, lo+1)
            frac = idx - lo
            return data[lo] + (data[hi]-data[lo]) * frac
        return self._heights[2]  # type: ignore

    @staticmethod
    def _parabolic(i: int, d: int, h: List[float], n: List[int]) -> float:
        n0, n1, n2 = n[i-1], n[i], n[i+1]
        h0, h1, h2 = h[i-1], h[i], h[i+1]
        return h1 + d / (n2 - n0) * ((n1 - n0 + d) * (h2 - h1) / (n2 - n1) + (n2 - n1 - d) * (h1 - h0) / (n1 - n0))

    @staticmethod
    def _linear(i: int, d: int, h: List[float], n: List[int]) -> float:
        return h[i] + d * (h[i + d] - h[i]) / (n[i + d] - n[i])


__all__ = ["P2Quantile"]
