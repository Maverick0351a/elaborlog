"""Promote the latest benchmark result to the committed baseline.

Usage:
  python scripts/update_baseline.py --result bench-result.json --baseline bench/baseline.json

Safety:
  - Refuses to overwrite when result lines/sec < existing baseline unless --force.
  - Writes atomically via temp file + replace.

Typical flow after an intentional perf improvement:
  1. Run benchmark multiple times; record median lines/sec.
  2. Ensure improvement is statistically meaningful (low variance, code rationale).
  3. Promote using this script (optionally --force if baseline was placeholder or noisy).
  4. Commit updated baseline.json with a concise explanation in the commit message.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

def load(path: Path) -> Dict[str, Any]:
    try:
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)

def write_atomic(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    os.replace(tmp, path)

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description='Promote benchmark result to baseline')
    ap.add_argument('--result', type=Path, default=Path('bench-result.json'))
    ap.add_argument('--baseline', type=Path, default=Path('bench/baseline.json'))
    ap.add_argument('--force', action='store_true', help='Force overwrite even if not faster')
    args = ap.parse_args(argv)

    result = load(args.result)
    if 'lines_per_sec' not in result:
        print('ERROR: result missing lines_per_sec', file=sys.stderr)
        return 1
    try:
        lps_new = float(result['lines_per_sec'])
    except (TypeError, ValueError):
        print('ERROR: result lines_per_sec not numeric', file=sys.stderr)
        return 1

    baseline = load(args.baseline)
    lps_old = float(baseline.get('lines_per_sec', 0) or 0)

    if lps_old and lps_new < lps_old and not args.force:
        print(f"Refusing to overwrite: new {lps_new:.2f} < baseline {lps_old:.2f} (use --force)", file=sys.stderr)
        return 2

    new_data = {
        'lines_per_sec': lps_new,
        'note': 'Updated via update_baseline.py (ensure commit message documents rationale)'
    }
    write_atomic(args.baseline, new_data)
    print(json.dumps({'old': lps_old, 'new': lps_new, 'updated': True}, indent=2))
    return 0

if __name__ == '__main__':  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
