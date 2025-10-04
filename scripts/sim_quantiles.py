#!/usr/bin/env python
"""Simulation harness (stub) for evaluating streaming quantile accuracy & alert dynamics.

Quick win scaffold: does not implement scenarios yet—intended to be iteratively filled in.

Planned scenarios (TODO):
1. Stationary distribution (Normal, LogNormal) -> measure absolute q error over time.
2. Mean shift at T (abrupt drift) -> measure detection latency until threshold adapts.
3. Gradual drift (linear mean increase) -> measure tracking error envelope.
4. Burst anomalies (mixture injection) -> approximate precision/recall vs configured quantile.
5. Multi-quantile mode comparison (q1 < q2 < q3) -> cross-plot convergence times.

Outputs (future): JSON report with metrics and optional matplotlib summary.

Run (future API):
    python scripts/sim_quantiles.py --samples 50000 --q 0.995 --scenario shift --shift-at 20000

Current state: only argument parsing + placeholder execution.
"""
from __future__ import annotations
import argparse
import json
import math
import random
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class ScenarioConfig:
    name: str
    samples: int
    quantiles: List[float]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("sim-quantiles", description="Streaming quantile simulation stub")
    p.add_argument("--samples", type=int, default=10000, help="Number of synthetic samples")
    p.add_argument("--quantiles", nargs="*", type=float, default=[0.99], help="Target quantiles")
    p.add_argument("--scenario", choices=["stationary", "shift", "gradual", "burst"], default="stationary")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", help="Write JSON results stub to this file")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    cfg = ScenarioConfig(name=args.scenario, samples=args.samples, quantiles=args.quantiles)
    # Placeholder synthetic data summary only
    summary: Dict[str, Any] = {
        "scenario": cfg.name,
        "samples": cfg.samples,
        "quantiles": cfg.quantiles,
        "note": "Simulation logic not yet implemented (stub).",
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"Wrote stub results to {args.out}")
    else:
        print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":  # pragma: no cover - trivial script stub
    raise SystemExit(main())
