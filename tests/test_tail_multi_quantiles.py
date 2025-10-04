import json
import tempfile
from pathlib import Path
from subprocess import run, PIPE


def write_log(path: Path, n: int = 400):
    lines = []
    for i in range(n):
        if i % 120 == 0:
            lines.append(f"ERROR critical spike id={i}\n")
        elif i % 40 == 0:
            lines.append(f"WARN anomaly code={i}\n")
        else:
            lines.append(f"INFO heartbeat seq={i}\n")
    path.write_text("".join(lines))


def test_tail_multi_quantiles_highest_used():
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "app.log"
        log_path.write_text("")
        write_log(log_path, 400)
        jsonl = Path(d) / "alerts.jsonl"
        # Use multi quantiles; small burn-in so we produce some alerts
        proc = run(
            [
                "python","-m","elaborlog.cli","tail", str(log_path),
                "--quantiles","0.99","0.995","0.998",
                "--burn-in","80","--window","150","--stats-interval","0", "--jsonl", str(jsonl), "--no-color","--no-follow"
            ],
            stdout=PIPE, stderr=PIPE, text=True, timeout=20
        )
        # Expect process to terminate after processing file once (window mode)
        assert proc.returncode == 0
        lines = jsonl.read_text().strip().splitlines()
        # Some alerts should have fired
        assert len(lines) > 0
        last = json.loads(lines[-1])
        # quantile field should equal highest requested
        assert abs(last["quantile"] - 0.998) < 1e-9
