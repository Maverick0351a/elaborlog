"""Benchmark regression guard.

Reads the current benchmark result JSON (produced by benchmark job)
and compares lines/sec against baseline. Fails (non-zero exit) if
performance regresses beyond allowed tolerance.

Usage:
  python scripts/check_benchmark.py --current bench-result.json \
      --baseline bench/baseline.json --min-ratio 0.90

CI Strategy:
  1. Run benchmark to produce bench-result.json (ensure JSON output).
  2. Run this script with chosen --min-ratio (e.g. 0.90 = allow <=10% drop).
  3. If regression detected, exit code 2.

Baseline Guidance:
  Establish baseline on a stable runner; update only when intentional
  performance improvements land. Commit baseline JSON to repo for deterministic checks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Benchmark regression checker")
    parser.add_argument("--current", required=True, type=Path, help="Path to current benchmark result JSON")
    parser.add_argument("--baseline", required=True, type=Path, help="Path to baseline benchmark JSON")
    parser.add_argument("--min-ratio", type=float, default=0.90, help="Minimum acceptable current/baseline lines_per_sec ratio (default 0.90)")

    args = parser.parse_args(argv)

    current = load_json(args.current)
    baseline = load_json(args.baseline)

    def extract(d: Dict[str, Any], label: str) -> float:
        if "lines_per_sec" not in d:
            print(f"ERROR: missing 'lines_per_sec' in {label} file", file=sys.stderr)
            sys.exit(1)
        try:
            return float(d["lines_per_sec"])
        except (TypeError, ValueError):
            print(f"ERROR: 'lines_per_sec' in {label} not numeric", file=sys.stderr)
            sys.exit(1)

    cur = extract(current, "current")
    base = extract(baseline, "baseline")

    if base <= 0:
        print("WARNING: baseline lines_per_sec <= 0; treating as pass (needs initialization)")
        return 0

    ratio = cur / base

    print(json.dumps({
        "baseline_lines_per_sec": base,
        "current_lines_per_sec": cur,
        "ratio": ratio,
        "min_ratio": args.min_ratio,
        "pass": ratio >= args.min_ratio
    }, indent=2))

    if ratio < args.min_ratio:
        print(
            f"PERF REGRESSION: ratio {ratio:.3f} < min_ratio {args.min_ratio:.3f}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - small script
    sys.exit(main(sys.argv[1:]))
