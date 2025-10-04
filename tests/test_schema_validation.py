import json, subprocess, sys, tempfile, os, re

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
        proc = subprocess.Popen([sys.executable, '-m', 'elaborlog.cli', 'tail', log, '--quantile', '0.5', '--burn-in', '0', '--jsonl', jsonl], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # Append a few lines to trigger alerts
            for i in range(5):
                with open(log, 'a', encoding='utf-8') as f:
                    f.write(f'ERROR something bad happened code={40+i} user={7+i}\n')
            # Give process time to emit
            proc.terminate()
            proc.wait(timeout=3)
        finally:
            if proc.poll() is None:
                proc.kill()
        # Load schema
        schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas', 'alert.schema.json')
        schema = json.loads(open(schema_path, 'r', encoding='utf-8').read())
        validator = jsonschema.Draft202012Validator(schema)  # type: ignore
        # Validate first alert line
        with open(jsonl, 'r', encoding='utf-8') as jf:
            line = jf.readline().strip()
            assert line, 'No alert JSON written'
            obj = json.loads(line)
            validator.validate(obj)
