import json
import tempfile
from pathlib import Path
from subprocess import run, PIPE

def write_alert_source(path: Path, n: int = 120):
    lines = []
    for i in range(n):
        if i % 37 == 0:
            lines.append(f"ERROR anomaly burst id={i}\n")
        elif i % 17 == 0:
            lines.append(f"WARN slowdown ms={i}\n")
        else:
            lines.append(f"INFO ok seq={i}\n")
    path.write_text("".join(lines))


def test_summarize_cli_basic():
    with tempfile.TemporaryDirectory() as d:
        log = Path(d)/"app.log"
        write_alert_source(log, 140)
        alerts = Path(d)/"alerts.jsonl"
        # Generate alerts (window for deterministic threshold, one-shot)
        p = run([
            "python","-m","elaborlog.cli","tail", str(log),
            "--quantiles","0.99","0.995","0.998","--window","120","--burn-in","40","--jsonl", str(alerts), "--no-follow", "--no-color"
        ], stdout=PIPE, stderr=PIPE, text=True, timeout=25)
        assert p.returncode == 0, p.stderr
        assert alerts.exists() and alerts.stat().st_size > 0
        out_summary = Path(d)/"summary.json"
        s = run([
            "python","-m","elaborlog.cli","summarize", str(alerts), "--out", str(out_summary), "--top-templates","5","--top-tokens","5"
        ], stdout=PIPE, stderr=PIPE, text=True, timeout=10)
        assert s.returncode == 0, s.stderr
        data = json.loads(out_summary.read_text())
        # Basic keys
        for k in ["alerts","novelty_min","novelty_max","top_templates","top_tokens"]:
            assert k in data
        assert data["alerts"] > 0
        assert isinstance(data["top_templates"], list)
        assert isinstance(data["top_tokens"], list)
