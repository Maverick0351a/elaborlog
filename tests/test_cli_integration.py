import sys
import json
import subprocess
from pathlib import Path


def run_cli(args, cwd=None):
    proc = subprocess.run([sys.executable, "-m", "elaborlog.cli", *args], capture_output=True, text=True, cwd=cwd)
    return proc


def make_log(tmp_path: Path) -> Path:
    content = """2025-10-04T00:00:00Z INFO startup complete
2025-10-04T00:00:01Z ERROR failed to connect host=alpha retry=1
2025-10-04T00:00:02Z WARN retrying connection host=alpha attempt=2
2025-10-04T00:00:03Z INFO heartbeat seq=1
2025-10-04T00:00:04Z INFO heartbeat seq=2
"""
    p = tmp_path / "app.log"
    p.write_text(content, encoding="utf-8")
    return p


def test_rank_json_output(tmp_path):
    log = make_log(tmp_path)
    json_out = tmp_path / "rank.json"
    proc = run_cli([
        "rank",
        str(log),
        "--json",
        str(json_out),
        "--no-color",
        "--top",
        "5",
    ])
    assert proc.returncode == 0, proc.stderr
    assert json_out.exists()
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert len(data) == 5
    assert all("novelty" in obj for obj in data)
    # Ensure scoring keys present
    assert {"score", "token_info_bits", "template_info_bits"}.issubset(data[0].keys())


def test_explain_json_output(tmp_path):
    log = make_log(tmp_path)
    json_out = tmp_path / "explain.json"
    # Pick one log line to explain
    line_to_explain = "ERROR failed to connect host=alpha retry=1"
    proc = run_cli([
        "explain",
        str(log),
        "--line",
        line_to_explain,
        "--json",
        str(json_out),
        "--no-color",
    ])
    assert proc.returncode == 0, proc.stderr
    data = json.loads(json_out.read_text(encoding="utf-8"))
    for key in ["novelty", "score", "token_info_bits", "template", "token_contributors"]:
        assert key in data, f"missing {key} in explain output"
    assert isinstance(data["token_contributors"], list)


def test_cluster_output(tmp_path):
    log = make_log(tmp_path)
    proc = run_cli(["cluster", str(log), "--top", "3", "--no-color"])
    assert proc.returncode == 0, proc.stderr
    # Expect at least two lines of output (count + template)
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln]
    assert len(lines) >= 2
    # Each line should start with a count (digits)
    assert all(line.split()[0].isdigit() for line in lines[:2])


def test_version_subcommand():
    proc = run_cli(["version"])  # returns elaborlog X.Y.Z
    assert proc.returncode == 0
    assert proc.stdout.lower().startswith("elaborlog ")
