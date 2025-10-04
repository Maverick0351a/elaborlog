import re, subprocess, sys

def test_bench_subcommand_smoke():
    proc = subprocess.run([sys.executable, '-m', 'elaborlog.cli', 'bench', '--lines', '2000', '--warm', '200', '--measure', '500'], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout + proc.stderr
    # Look for throughput line
    m = re.search(r'Processed\s+500\s+lines in .*? -> \d+[,.]?\d* lines/sec', out)
    assert m, f"Missing throughput output. Got: {out}"
