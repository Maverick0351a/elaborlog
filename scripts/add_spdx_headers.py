#!/usr/bin/env python
"""Add SPDX license identifiers to Python source files lacking them.

Dry-run by default; pass --write to modify files in place.
Skips files in build, dist, .venv, and egg-info directories.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

SPDX_LINE = "# SPDX-License-Identifier: Apache-2.0\n"

EXCLUDE_DIRS = {"build", "dist", ".venv", "__pycache__"}


def wants(path: Path) -> bool:
    if path.suffix != ".py":
        return False
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return False
    if any(p.endswith(".egg-info") for p in parts):  # crude but fine for helper
        return False
    return True


def process(path: Path, write: bool) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    if "SPDX-License-Identifier" in text.splitlines()[:3]:
        return False
    if write:
        new = SPDX_LINE + text
        path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Add SPDX headers to Python files")
    ap.add_argument("--root", default=".", help="Root directory to scan")
    ap.add_argument("--write", action="store_true", help="Apply changes (otherwise dry-run)")
    args = ap.parse_args()
    root = Path(args.root)
    added = 0
    scanned = 0
    for p in root.rglob("*.py"):
        if not wants(p):
            continue
        scanned += 1
        if process(p, args.write):
            added += 1
    print(f"Scanned {scanned} python files; headers added to {added} (write={args.write})")
    return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
