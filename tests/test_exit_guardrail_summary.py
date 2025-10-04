import subprocess
import sys


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def test_rank_guardrail_summary(tmp_path):
    # Create a file with a very long line to trigger truncation and token truncation
    log_path = tmp_path / "log.txt"
    # Create an overlong line to trigger truncation (default max_line_length=2000)
    long_line = "INFO " + ("A" * 3000) + "\n"
    log_path.write_text(long_line, encoding="utf-8")
    code, out, err = _run([sys.executable, "-m", "elaborlog.cli", "rank", str(log_path)])
    assert code == 0
    assert "summary:" in err
    assert "truncated_lines=" in err


def test_explain_guardrail_summary(tmp_path):
    # Use a prime file with very long line so truncation occurs during priming
    prime_path = tmp_path / "prime.txt"
    long_line = "INFO " + " ".join([f"tok{i}" for i in range(800)]) + "\n"
    prime_path.write_text(long_line, encoding="utf-8")
    # Provide a shorter line for explanation to avoid OS command length limits
    short_line = "INFO example explanation line"
    code, out, err = _run([sys.executable, "-m", "elaborlog.cli", "explain", str(prime_path), "--line", short_line])
    assert code == 0
    assert "summary:" in err


def test_tail_guardrail_summary(tmp_path):
    import sys as _sys
    if _sys.platform.startswith('win'):
        import pytest as _pytest
        _pytest.skip("Tail summary test skipped on Windows due to terminate() not executing cleanup")
    # Start tail first, then append a long line so tail reads it (like actual streaming scenario)
    log_path = tmp_path / "tail.txt"
    log_path.write_text("", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "elaborlog.cli", "tail", str(log_path), "--burn-in", "0", "--quantile", "0.95"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    long_line = "INFO " + " ".join([f"tok{i}" for i in range(800)]) + "\n"
    # Append after process starts
    import time
    time.sleep(0.3)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(long_line)
    time.sleep(0.8)
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
    stderr = proc.stderr.read()
    assert "summary:" in stderr, f"stderr did not contain summary: {stderr!r}"
