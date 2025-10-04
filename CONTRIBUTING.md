# Contributing to Elaborlog

Thanks for your interest in improving Elaborlog! This document lays out the lightweight
standards that keep the codebase consistent and performant while staying friendly to
first‑time contributors.

## Quick Start

1. Fork & clone the repo
2. Create a virtual environment (Python >= 3.9)
3. Install dev extras:
   ```bash
   pip install -e '.[dev,server,color]'
   ```
4. Run tests & type checks:
   ```bash
   pytest -q
   mypy
   ruff check src
   ```
5. (Optional but recommended) Install pre-commit hooks for automatic lint & type checks on commit:
  ```bash
  pre-commit install
  ```
  You can run them manually across the whole repo anytime:
  ```bash
  pre-commit run --all-files
  ```
6. Open a PR with a concise title & motivation paragraph.

## Coding Style

- Use **PEP 585** built‑in generics (`list[str]`, `dict[str, float]`) – no `List` / `Dict` imports
  unless required for older typing constructs.
- Keep functions small; prefer extracting helpers to long inline blocks.
- Avoid premature optimization but keep hot paths allocation‑light (see `tokenize.py`).
- Use f‑strings for clarity; avoid `.format(...)` unless dynamic field selection is needed.
- Public APIs (CLI flags, JSON field names, schemas) are considered stable once released.

## Logging & Errors

- Use `elaborlog.logutil.get_logger()` instead of `print` for warnings. Ordinary user‑visible
  operational messages (CLI progress, summaries) can still use `print` to stdout/stderr.
- Never swallow exceptions silently. If you defensively catch a broad exception, log a warning
  and add a brief comment justifying it.

## Testing

- Favor **behavioral tests** that exercise CLI or service boundaries over microscopic unit tests.
- New features should add or extend tests under `tests/` – aim for >90% diff coverage.
- Keep subprocess‑based tests short (<2s) and mark longer ones with `@pytest.mark.timeout`.
- Schema or optional dependency tests should `skip` gracefully if the dependency is absent.

## Type Checking

- Mypy runs in CI with `disallow_untyped_defs = true`. Annotate all new function arguments and
  return types (private helpers too).
- If a third‑party lib lacks stubs, use a focused `# type: ignore[code]` (not a bare ignore) and
  add a comment referencing an upstream issue if applicable.

## Performance Benchmarks

- The synthetic benchmark (`elaborlog bench` or `bench/benchmark.py`) serves as a coarse regression
  detector. Avoid adding large per‑line allocations in the scoring loop.
- If your change materially improves performance (or trades perf for clarity), document before/after
  lines/sec in the PR description.

## JSON Schemas & Backward Compatibility

- Schema changes live in `schemas/`. Reuse `$defs` for shared shapes. Add new optional fields using
  permissive defaults; avoid removing or renaming existing fields in a minor release.
- Update tests validating schemas if you extend them.

## CLI Flags

- Keep flag names short and explicit. Provide `--no-*` negations only when it meaningfully toggles
  a default behavior.
- Group related flags (masking/tokenization/weights) near each other in the subcommand builder.

## Snapshots / Model Persistence

- Increment snapshot `version` only if the serialized shape changes. Provide upgrade logic for older
  versions so users can upgrade without model loss.

## Git & Commits

- Conventional prefixes encouraged (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`).
- Keep commits logically atomic – mechanical refactors separate from behavior changes.

## Opening Issues

Please include:
- Reproduction steps (CLI command or code snippet)
- Sample log line(s) if relevant (sanitize secrets!)
- Expected vs actual behavior
- Environment: OS, Python version, elaborlog version

## Security

Do not open public issues for potential vulnerabilities. Instead, contact the maintainers privately
(or remove sensitive specifics and describe the class of issue).

## Release Checklist (Maintainers)

1. Ensure CI is green (tests, type checks, coverage, benchmark does not regress materially)
2. Update `CHANGELOG.md` (Added / Changed / Fixed / Migration Notes)
3. Bump version in `pyproject.toml` and `__init__.py`
4. Tag: `git tag -a vX.Y.Z -m 'Release X.Y.Z'` & push tag
5. Build & publish: `python -m build` then `twine upload dist/*`
6. Verify PyPI metadata / badges

Happy hacking! ✨
