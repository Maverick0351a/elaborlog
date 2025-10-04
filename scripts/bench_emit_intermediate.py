"""Micro benchmark for --emit-intermediate and --all-token-contributors overhead.

Usage (from repo root):

    python -m scripts.bench_emit_intermediate --lines 50000 --quantiles 0.95 0.99 0.999

It fabricates a synthetic log stream with controlled template variability, runs
three configurations of the tail engine in-process, and reports relative wall
clock times:

1. baseline: highest quantile, truncated contributors
2. emit-intermediate: adds quantile_estimates field
3. full contributors: emit-intermediate + all-token-contributors

This is intentionally lightweight (no external deps beyond stdlib) and gives a
quick local signal. For rigorous benchmarking, use `elaborlog bench` harness.
"""
from __future__ import annotations

import argparse
import random
import string
import time
from dataclasses import dataclass
from typing import List, Sequence

# We import internal modules directly (bench script, not part of library API stability)
from elaborlog.tail import TailEngine  # type: ignore
from elaborlog.parsers import LineParser  # type: ignore
from elaborlog.config import TailConfig  # type: ignore


def synthetic_line(tpl_id: int, noise_tokens: Sequence[str]) -> str:
    base = f"ERROR payment declined code={400+tpl_id} user={1000+tpl_id}"
    # sprinkle 0-2 random noise tokens to vary token distribution
    k = random.randint(0, 2)
    if k:
        extra = " ".join(random.choice(noise_tokens) for _ in range(k))
        return f"{base} {extra}"
    return base


def gen_corpus(n: int, distinct: int, seed: int = 0) -> List[str]:
    random.seed(seed)
    noise_tokens = ["tok" + c for c in string.ascii_lowercase[:16]]
    return [synthetic_line(i % distinct, noise_tokens) for i in range(n)]


@dataclass
class RunResult:
    label: str
    seconds: float
    alerts: int


def run_once(lines: Sequence[str], quantiles: Sequence[float], emit: bool, full: bool) -> RunResult:
    cfg = TailConfig(
        quantiles=list(quantiles),
        window=None,
        burn_in=100,
        emit_intermediate=emit,
        all_token_contributors=full,
        follow=False,
    )
    parser = LineParser(split_camel=False, split_dot=False, mask_patterns=[], mask_order=[], max_tokens_per_line=None)
    engine = TailEngine(config=cfg, parser=parser)
    start = time.perf_counter()
    alerts = 0
    for ln, line in enumerate(lines):
        out = engine.process_line(line, lineno=ln)
        if out is not None:
            alerts += 1
    elapsed = time.perf_counter() - start
    label = "baseline" if not emit and not full else ("emit-intermediate" if emit and not full else "full+emit")
    return RunResult(label=label, seconds=elapsed, alerts=alerts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=30000, help="Synthetic lines to generate")
    ap.add_argument("--distinct", type=int, default=500, help="Distinct templates")
    ap.add_argument("--quantiles", type=float, nargs="+", default=[0.99], help="Quantiles to track")
    args = ap.parse_args()

    corpus = gen_corpus(args.lines, args.distinct)

    runs = [
        run_once(corpus, args.quantiles, emit=False, full=False),
        run_once(corpus, args.quantiles, emit=True, full=False),
        run_once(corpus, args.quantiles, emit=True, full=True),
    ]

    baseline = runs[0].seconds
    print("config,seconds,alerts,slowdown_vs_baseline")
    for r in runs:
        slowdown = r.seconds / baseline if baseline > 0 else 0.0
        print(f"{r.label},{r.seconds:.4f},{r.alerts},{slowdown:.3f}")


if __name__ == "__main__":  # pragma: no cover
    main()
