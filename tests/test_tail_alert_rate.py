import subprocess, sys, tempfile, time, textwrap, re, os


def test_tail_alert_rate_stats():
    # Create a temporary log file and append lines gradually to trigger stats
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, 'live.log')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('INFO start\n')
        # Launch tail subprocess
        proc = subprocess.Popen([sys.executable, '-m', 'elaborlog.cli', 'tail', path, '--stats-interval', '0.2', '--quantile', '0.8', '--burn-in', '5'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # Append lines
            for i in range(120):  # ensure duration exceeds stats interval while lines flow
                with open(path, 'a', encoding='utf-8') as f:
                    f.write(f'INFO iteration {i}\n')
                time.sleep(0.005)
            time.sleep(0.4)  # brief settle time
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
        stderr_out = proc.stderr.read()
        # Look for stats line
    assert re.search(r'\[elaborlog\] stats: lines=\d+ alerts=\d+ observed_rate=\d+\.\d{4} target_quantile=0\.8(?:0+)?', stderr_out), stderr_out
