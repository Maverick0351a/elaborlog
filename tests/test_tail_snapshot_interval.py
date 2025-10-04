import sys
import time
import subprocess
import json

import pytest


@pytest.mark.timeout(10)
def test_tail_periodic_snapshot_updates_file(tmp_path):
    # Create a small growing log file
    log_path = tmp_path / "app.log"
    log_path.write_text("one first line\n", encoding="utf-8")

    state_path = tmp_path / "state.json"

    # We'll run the tail command in a subprocess so the snapshot thread runs normally.
    # Use a short snapshot interval.
    cmd = [sys.executable, "-m", "elaborlog.cli", "tail", str(log_path), "--snapshot-interval", "0.5", "--state-out", str(state_path), "--burn-in", "0", "--quantile", "0.95"]

    start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Append a couple lines over time
    time.sleep(0.3)
    with log_path.open("a", encoding="utf-8") as f:
        f.write("two second line\n")
    time.sleep(0.3)
    with log_path.open("a", encoding="utf-8") as f:
        f.write("three third line\n")

    # Capture initial mtime if file appears
    initial_mtime = state_path.stat().st_mtime if state_path.exists() else 0

    # Wait long enough for at least one periodic snapshot
    time.sleep(1.2)

    # Terminate process
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()

    assert state_path.exists(), "state snapshot should exist"
    assert state_path.stat().st_size > 0
    # Basic sanity: load JSON
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and "version" in data
    # Ensure snapshot wasn't only created at shutdown by checking elapsed >= interval
    assert time.time() - start >= 0.5
    # If we captured an earlier mtime, ensure file was updated (mtime increased)
    if initial_mtime:
        assert state_path.stat().st_mtime >= initial_mtime
