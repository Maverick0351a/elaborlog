import json, subprocess, sys, tempfile, os

try:
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover
    jsonschema = None


def load_schema(name: str):
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
    with open(os.path.join(base, name), 'r', encoding='utf-8') as f:
        return json.load(f)


def test_rank_schema_validation():
    if jsonschema is None:
        import pytest
        pytest.skip('jsonschema not installed')
    schema = load_schema('rank.schema.json')
    validator = jsonschema.Draft202012Validator(schema)  # type: ignore
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, 'r.log')
        with open(log, 'w', encoding='utf-8') as f:
            f.write('ERROR alpha failed code=1 user=1\n')
            f.write('INFO beta ok user=2\n')
            f.write('WARN gamma slow latency=120ms user=3\n')
        out_json = os.path.join(td, 'rank.json')
        proc = subprocess.run([sys.executable, '-m', 'elaborlog.cli', 'rank', log, '--json', out_json], capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        data = json.loads(open(out_json, 'r', encoding='utf-8').read())
        assert isinstance(data, list)
        assert data, 'Expected non-empty ranked output'
        validator.validate(data)


def test_explain_schema_validation():
    if jsonschema is None:
        import pytest
        pytest.skip('jsonschema not installed')
    rank_schema = load_schema('explain.schema.json')
    validator = jsonschema.Draft202012Validator(rank_schema)  # type: ignore
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, 'e.log')
        with open(log, 'w', encoding='utf-8') as f:
            f.write('ERROR alpha failed code=1 user=1\n')
            f.write('INFO beta ok user=2\n')
        out_json = os.path.join(td, 'explain.json')
        line = 'ERROR alpha failed code=1 user=1'
        proc = subprocess.run([sys.executable, '-m', 'elaborlog.cli', 'explain', log, '--line', line, '--json', out_json], capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        obj = json.loads(open(out_json, 'r', encoding='utf-8').read())
        validator.validate(obj)
