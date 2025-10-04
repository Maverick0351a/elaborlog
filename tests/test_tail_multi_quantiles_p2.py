import json
import tempfile
from pathlib import Path
from subprocess import run, PIPE

def write_log(path: Path, n: int = 350):
    # Similar structure; variety of severities to exercise scoring.
    lines = []
    for i in range(n):
        if i % 100 == 0:
            lines.append(f"ERROR payment decline id={i}\n")
        elif i % 33 == 0:
            lines.append(f"WARN slow query ms={i}\n")
        else:
            lines.append(f"INFO ok seq={i}\n")
    path.write_text("".join(lines))


def test_tail_multi_quantiles_p2_highest_used():
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "app.log"
        write_log(log_path, 350)
        jsonl = Path(d) / "alerts.jsonl"
        # Use P2 streaming mode (no --window) with multiple quantiles and a modest burn-in
        proc = run(
            [
                "python","-m","elaborlog.cli","tail", str(log_path),
                "--quantiles","0.99","0.995","0.998",
                "--burn-in","60","--stats-interval","0", "--jsonl", str(jsonl), "--no-color","--no-follow"
            ],
            stdout=PIPE, stderr=PIPE, text=True, timeout=20
        )
        assert proc.returncode == 0, proc.stderr
        data = jsonl.read_text().strip().splitlines()
        assert data, "Expected at least one alert"
        last = json.loads(data[-1])
        assert abs(last["quantile"] - 0.998) < 1e-9
