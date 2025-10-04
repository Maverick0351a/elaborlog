import json
import os
import subprocess
import sys
import tempfile
import time

try:
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover
    jsonschema = None


def test_alert_schema_validates_basic_alert():
    if jsonschema is None:
        import pytest
        pytest.skip('jsonschema not installed')
    # Generate a single alert by forcing a low threshold
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, 'a.log')
        with open(log, 'w', encoding='utf-8') as f:
            f.write('ERROR something bad happened code=42 user=7\n')
        jsonl = os.path.join(td, 'alerts.jsonl')
    # Use a direct threshold so alerts fire immediately.
        proc = subprocess.Popen([
            sys.executable,
            '-m',
            'elaborlog.cli',
            'tail',
            log,
            '--threshold', '0.0',
            '--burn-in', '0',
            '--jsonl', jsonl,
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # Allow tail loop to start
            time.sleep(0.3)
            # Append a few lines to trigger alerts
            for i in range(8):
                with open(log, 'a', encoding='utf-8') as f:
                    f.write(f'ERROR something bad happened code={40+i} user={7+i}\n')
                time.sleep(0.05)
            # Poll for non-empty JSONL
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if os.path.exists(jsonl) and os.path.getsize(jsonl) > 0:
                    break
                time.sleep(0.1)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        finally:
            if proc.poll() is None:
                proc.kill()
        # Load schema
        schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas', 'alert.schema.json')
        schema = json.loads(open(schema_path, 'r', encoding='utf-8').read())
        validator = jsonschema.Draft202012Validator(schema)  # type: ignore
        # Validate first alert line
        assert os.path.exists(jsonl), f"alerts jsonl file not created; stderr={proc.stderr.read() if proc.stderr else 'n/a'}"
        with open(jsonl, 'r', encoding='utf-8') as jf:
            line = jf.readline().strip()
            assert line, 'No alert JSON written'
            obj = json.loads(line)
            validator.validate(obj)
