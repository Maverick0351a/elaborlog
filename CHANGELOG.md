# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog and adheres to semantic-ish versioning while pre-1.0.

## [0.2.0] - 2025-10-03
### Added
- Streaming P² quantile estimator for tail alerting (default) replacing O(W log W) resort; fallback to window quantile via `--window`.
- Lazy decay with global scale factor (`g`) eliminating O(V) decay scans.
- Weight override flags: `--w-token`, `--w-template`, `--w-level` across rank/score/tail/explain.
- JSON outputs:
  - `rank|score --json` writes full array including token/template info bits and top token contributors.
  - `tail --jsonl` enhanced per-alert JSONL (token contributors, threshold metadata, template probability).
  - `explain --json` structured explanation with weights and token contributors.
- Guardrails: `max_line_length` & `max_tokens_per_line` with counters (snapshot persisted).
- Snapshot version bumped to 3 (includes decay scale factor and guardrail counters). Backward compatibility with v1/v2 snapshots maintained.
- Extensive new tests: streaming quantile correctness, pruning invariants, guardrails, P² convergence, decay persistence.
- Regex pipeline optimization: consolidated into ordered pattern list for marginal performance gain.
- Type annotations on public `InfoModel` API and PEP 561 marker.

### Changed
- README expanded with JSON schemas, lazy decay explanation, guardrails, snapshot v3.
- Alert JSON field names standardized (`token_info_bits`, `template_info_bits`).

### Removed
- (None)

### Migration Notes
- Old snapshots (version 1 or 2) still load; new saves produce version 3 automatically.
- If you depended on previous alert JSON keys `token_info` / `template_info`, update to `token_info_bits` / `template_info_bits`.

## [0.1.0] - 2025-09-XX
- Initial public release: token & template surprisal scoring, rolling quantile, CSV ranking, nearest neighbors, snapshot persistence, basic explain & cluster commands.

---

Unreleased changes will accumulate here until next tagged version.
