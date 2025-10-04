import contextlib
import json
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("fastapi")


def find_free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_metrics_endpoint():
    port = find_free_port()
    proc = subprocess.Popen([sys.executable, '-m', 'elaborlog.cli', 'serve', '--port', str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # wait briefly for server
        time.sleep(0.8)
        import urllib.request
        # Prime model with observe
        observe_req = urllib.request.Request(f'http://127.0.0.1:{port}/observe', data=b'{"line":"ERROR alpha failed code=1"}', headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(observe_req, timeout=2) as r:
            assert r.status == 200
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics', timeout=2) as r:
            assert r.status == 200
            data = json.loads(r.read().decode('utf-8'))
        # Basic keys
        for k in ["tokens", "templates", "total_tokens", "total_templates", "seen_lines", "g", "config"]:
            assert k in data
        assert data['tokens'] >= 1
        assert 'decay' in data['config']
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
