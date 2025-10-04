import subprocess, sys, re


def test_cli_version_matches_package():
    # Run the CLI with --version
    proc = subprocess.run([sys.executable, '-m', 'elaborlog.cli', '--version'], capture_output=True, text=True)
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).strip()
    # Expect something like: elaborlog X.Y.Z
    m = re.match(r'elaborlog\s+(\d+\.\d+\.\d+)', out)
    assert m, f'Unexpected version output: {out}'
    reported = m.group(1)
    # Import package version
    import elaborlog
    assert reported == elaborlog.__version__, f"CLI version {reported} != package {elaborlog.__version__}"
