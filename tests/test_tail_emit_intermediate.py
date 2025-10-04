import json
import tempfile
from pathlib import Path
from subprocess import run, PIPE

def make_log(path: Path, n: int = 300):
    lines = []
    for i in range(n):
        if i % 70 == 0:
            lines.append(f"ERROR spike v={i}\n")
        elif i % 25 == 0:
            lines.append(f"WARN drift k={i}\n")
        else:
            lines.append(f"INFO beat idx={i}\n")
    path.write_text("".join(lines))


def test_emit_intermediate_streaming():
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d)/"app.log"
        make_log(log_path, 300)
        out_jsonl = Path(d)/"alerts.jsonl"
        proc = run([
            "python","-m","elaborlog.cli","tail", str(log_path),
            "--quantiles","0.99","0.995","0.998",
            "--burn-in","50","--stats-interval","0","--jsonl", str(out_jsonl),
            "--emit-intermediate","--no-follow","--no-color"
        ], stdout=PIPE, stderr=PIPE, text=True, timeout=20)
        assert proc.returncode == 0, proc.stderr
        lines = [line for line in out_jsonl.read_text().splitlines() if line.strip()]
        assert lines, "Expected alerts"
        obj = json.loads(lines[-1])
        qmap = obj.get("quantile_estimates")
        assert qmap is not None, "quantile_estimates missing"
        # Highest quantile must match standalone quantile field
        assert abs(float(max(qmap.keys())) - obj["quantile"]) < 1e-9
        # All requested quantiles present
        for q in ("0.990","0.995","0.998"):
            assert q in qmap


def test_emit_intermediate_window():
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d)/"app.log"
        make_log(log_path, 320)
        out_jsonl = Path(d)/"alerts.jsonl"
        proc = run([
            "python","-m","elaborlog.cli","tail", str(log_path),
            "--quantiles","0.99","0.995","0.998","--window","160",
            "--burn-in","50","--stats-interval","0","--jsonl", str(out_jsonl),
            "--emit-intermediate","--no-follow","--no-color"
        ], stdout=PIPE, stderr=PIPE, text=True, timeout=20)
        assert proc.returncode == 0, proc.stderr
        lines = [line for line in out_jsonl.read_text().splitlines() if line.strip()]
        assert lines, "Expected alerts"
        obj = json.loads(lines[-1])
        qmap = obj.get("quantile_estimates")
        assert qmap is not None
        for q in ("0.990","0.995","0.998"):
            assert q in qmap
        assert abs(float(max(qmap.keys())) - obj["quantile"]) < 1e-9
