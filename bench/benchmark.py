"""Simple benchmarking harness for Elaborlog.

Measures throughput (lines/sec) and approximate memory growth while scoring
synthetic or real log files. Keeps dependencies minimal; for deeper profiling
integrate with py-spy or scalene externally.
"""
from __future__ import annotations

import argparse
import time
import tracemalloc
from pathlib import Path
from typing import Iterable

from elaborlog.parsers import parse_line
from elaborlog.score import InfoModel


def synthetic_lines(n: int) -> Iterable[str]:
    base = [
        "INFO user login success user=123",
        "WARN db connection slow latency=120ms host=db-primary",
        "ERROR payment declined code=402 user=9912 amount=1999",
        "INFO cache hit key=abcd1234",
        "INFO cache miss key=efgh5678",
    ]
    for i in range(n):
        yield base[i % len(base)] + f" seq={i}"


def iter_file(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            yield line.rstrip("\n")


def run(lines: Iterable[str], warm: int, measure: int) -> None:
    model = InfoModel()
    # Warm phase (populate frequencies but ignore timing)
    for idx, line in enumerate(lines):
        if idx >= warm:
            break
        _, _, msg = parse_line(line)
        model.observe(msg)
    # Rebuild iterator for measurement phase if needed
    if isinstance(lines, list):
        to_measure: Iterable[str] = lines[warm : warm + measure]
    else:
        # Regenerate synthetic if generator consumed
        to_measure = synthetic_lines(measure)

    tracemalloc.start()
    start = time.perf_counter()
    counted = 0
    for counted, line in enumerate(to_measure, start=1):
        _, _, msg = parse_line(line)
        model.observe(msg)
        model.score(msg)
    elapsed = time.perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    lps = counted / elapsed if elapsed else float("inf")
    print(f"Processed {counted} lines in {elapsed:.3f}s -> {lps:,.0f} lines/sec")
    print(f"Current mem ~{current/1024/1024:.2f} MB; Peak mem ~{peak/1024/1024:.2f} MB")
    print(f"Unique tokens: {len(model.token_counts)}  templates: {len(model.template_counts)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark Elaborlog scoring throughput")
    ap.add_argument("--file", help="Optional log file to benchmark against")
    ap.add_argument("--lines", type=int, default=20000, help="Synthetic lines to generate if no file")
    ap.add_argument("--warm", type=int, default=2000, help="Warm-up lines (not timed)")
    ap.add_argument("--measure", type=int, default=10000, help="Lines to measure")
    args = ap.parse_args()

    if args.file:
        p = Path(args.file)
        if not p.exists():
            raise SystemExit(f"File not found: {p}")
        content = list(iter_file(p))
        if len(content) < args.warm + args.measure:
            # Extend by cycling
            needed = args.warm + args.measure - len(content)
            content.extend(content[:needed])
        run(content, args.warm, args.measure)
    else:
        run(list(synthetic_lines(args.lines)), args.warm, args.measure)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual use
    raise SystemExit(main())
