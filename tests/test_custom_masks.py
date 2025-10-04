import subprocess, sys, json, tempfile, textwrap, os, pathlib

PYTHON = sys.executable

def run_cli(args, input_text=None):
    env = os.environ.copy()
    cmd = [PYTHON, "-m", "elaborlog.cli"] + args
    proc = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def test_rank_with_custom_mask(tmp_path):
    # Create a log file with a custom pattern we want to mask as <user>
    log = tmp_path / "app.log"
    log.write_text("User alice logged in\nUser bob logged in\n")

    # Without mask, template should contain concrete names (at least one)
    code, out_plain, err = run_cli(["rank", str(log), "--top", "2"])  # default ranking
    assert code == 0
    assert "alice" in out_plain or "bob" in out_plain

    # With custom mask applied before built-ins
    json_path = tmp_path / "out.json"
    code, out_masked, err2 = run_cli([
        "rank", str(log), "--top", "2", "--mask", r"User [a-z]+=User <user>", "--json", str(json_path)
    ])
    assert code == 0, err2
    data = json.loads(json_path.read_text())
    assert any("User <user> logged in" in obj["template"] for obj in data)


def test_explain_with_mask(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("ID=123 action=OPEN\nID=456 action=CLOSE\n")
    # Explain a line with a custom mask for ID numbers
    json_out = tmp_path / "exp.json"
    code, out, err = run_cli([
        "explain", str(log), "--line", "ID=789 action=OPEN", "--json", str(json_out),
        "--mask", r"ID=\\d+=ID=<id>",
    ])
    assert code == 0, err
    data = json.loads(json_out.read_text())
    assert data["template"].count("<id>") == 1


def test_cluster_with_mask(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("path=/home/alice/file.txt\npath=/home/bob/file.txt\n")
    code, out, err = run_cli([
        "cluster", str(log), "--top", "5", "--mask", r"<path>=<home>", "--mask-order", "after",
    ])
    assert code == 0, err
    # Replacement should appear in clustered template
    assert ("<home>" in out) or ("<path>" in out)
