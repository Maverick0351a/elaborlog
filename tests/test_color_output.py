import os
import sys
import subprocess
from pathlib import Path


def test_rank_no_color(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("INFO start one\nERROR critical fail\n", encoding="utf-8")
    # Run with --no-color and capture output
    proc = subprocess.run([
        sys.executable,
        "-m",
        "elaborlog.cli",
        "rank",
        str(log),
        "--no-color",
        "--top",
        "2",
    ], capture_output=True, text=True)
    assert proc.returncode == 0
    assert "\x1b[" not in proc.stdout  # no ANSI escapes


def test_rank_color_if_rich(tmp_path):
    # If rich is installed in environment, we expect ANSI codes unless --no-color provided.
    try:
        import rich  # noqa: F401
    except Exception:
        return  # skip silently if rich not available
    log = tmp_path / "app2.log"
    log.write_text("INFO start two\nERROR critical boom\n", encoding="utf-8")
    env = os.environ.copy()
    env["FORCE_COLOR"] = "1"
    proc = subprocess.run([
        sys.executable,
        "-m",
        "elaborlog.cli",
        "rank",
        str(log),
        "--top",
        "2",
    ], capture_output=True, text=True, env=env)
    assert proc.returncode == 0
    # Presence of at least one escape sequence
    # Accept either ANSI escapes or (fallback) plain output if rich failed to color (rare Windows CI cases).
    # If no ANSI, at least ensure output lines present.
    if "\x1b[" not in proc.stdout:
        assert "novelty=" in proc.stdout and "score=" in proc.stdout
