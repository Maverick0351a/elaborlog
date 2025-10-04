from pathlib import Path
import sys

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore
else:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore


def test_pyproject_urls_exist():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    urls = data.get("project", {}).get("urls", {})
    required = ["Homepage", "Repository", "Issues", "Changelog"]
    for key in required:
        assert key in urls, f"Missing URL key: {key}"
        assert urls[key].startswith("https://"), f"URL for {key} must use https"
