# Elaborlog

![CI](https://github.com/Maverick0351a/elaborlog/actions/workflows/ci.yml/badge.svg) ![Coverage](https://codecov.io/gh/Maverick0351a/elaborlog/branch/main/graph/badge.svg)
<!-- PyPI badge placeholder: will activate after first release -->

Surface **rare, high‑signal** log lines and explain *why* they matter.

Fast streaming novelty scoring + adaptive quantile alerting + transparent token/template explanations.

## Why

Logs are overwhelming. You want the **needles**, not the hay. Elaborlog ranks lines by:

- **Token rarity** (Shannon self-information from online frequencies)
- **Template rarity** (structure-aware masking of IDs, timestamps, IPs)
- **Severity bonus** (small, transparent bump for ERROR/WARN)

It also shows **nearest neighbors** for instant context.

## Install

```bash
pip install -e ".[dev]"   # for local dev
# or
pipx install elaborlog    # after you publish to PyPI
```

(Optional) colorized output:

```bash
pip install "elaborlog[color]"
```

## Quickstart

Rank a file and print the top 20 most novel lines:

```bash
elaborlog rank examples/app.log --top 20
```

Write the full novelty-ranked CSV for later triage:

```bash
elaborlog rank examples/app.log --out ranked.csv
```

Tail live logs and alert on the rarest 0.8 % of lines with neighbor context:

```bash
elaborlog tail /var/log/app.log --mode triage
```

Escalate only the most exceptional outliers (≈0.5 %) and dedupe repeats:

```bash
elaborlog tail /var/log/app.log --mode page --dedupe-template
```

Explain why a single line popped, with the top surprisal tokens:

```bash
elaborlog explain examples/app.log --line "ERROR payment declined code=402 user=9922" --top-tokens 8
```

Show the most common templates:

```bash
elaborlog cluster examples/app.log --top 30
```

Need a tuned preset? Try `--profile web`, `--profile k8s`, or `--profile auth` to load sensible window/quantile knobs for that source.

Prefer bigrams for rigid formats? Add `--with-bigrams` to `rank`, `tail`, or `explain` when you know the templates are stable.

Need to rebalance scoring influences? Override weights on any scoring-related command:

```bash
elaborlog rank production.log --w-token 1.2 --w-template 0.8 --w-level 0.4
```

Stream alerts and also capture structured machine output:

```bash
elaborlog tail /var/log/app.log --mode triage --jsonl alerts.jsonl
```
Each JSONL alert includes: novelty, raw score (and component bits), template probability, top token contributors (token, bits, probability, frequency), neighbor lines, quantile meta.

Emit rolling alert rate stats (stderr) every 10s:

```bash
elaborlog tail /var/log/app.log --stats-interval 10
```

Batch JSON export:

```bash
elaborlog rank prod.log --json ranked.json
```

Structured single-line explanation:

```bash
elaborlog explain prod.log --line "ERROR payment declined code=402 user=9922" --json explain.json
```

### Run as a lightweight service

Install server extras and launch the HTTP API:

```bash
pip install "elaborlog[server]"
elaborlog serve --host 0.0.0.0 --port 8080 --state-out state.json
```

Endpoints:

- `GET /healthz` – liveness
- `POST /observe` – body `{ "line": "..." }` (updates frequencies)
- `POST /score` – body `{ "line": "..." }` returns scoring fields
- `GET /stats` – model cardinalities & counters
- `GET /metrics` – detailed internal metrics (counts, decay scale, renormalizations, guardrail counters)

You can warm start with `--state-in` and enable periodic snapshots with `--state-out` (every 60s by default, adjustable via `--interval`).

### Benchmarking

Use the bundled harness to gauge local throughput:

```bash
python bench/benchmark.py --lines 50000 --warm 5000 --measure 20000
```

Or benchmark a real file:

```bash
python bench/benchmark.py --file examples/app.log --warm 1000 --measure 5000
```

Output includes lines/sec, current & peak memory, and vocabulary sizes to help tune `max_tokens`/`max_templates`.

### Persisting model state (Snapshots v3)

Cold starts are optional now. Any scoring command can save and reuse the frequency model:

```bash
# Warm-start a streaming tail and persist after shutdown
elaborlog tail /var/log/app.log --mode triage --state-out state.json

# Resume later with the saved state (and keep updating it)
elaborlog tail /var/log/app.log --mode triage --state-in state.json --state-out state.json

# Batch scoring can also reuse the same snapshot
elaborlog rank production.log --state-in state.json --state-out state.json
```

Snapshots (version 3) include: config, token/template counts, decay scale factor (`g`), guardrail counters, and vocabulary sizes. Backward compatibility: older v1/v2 snapshots still load (new counters default to 0).

## Defaults at a glance

- **Canonicalization**: timestamps `<ts>`, IPs `<ip>`, UUIDs `<uuid>`, hex `<hex>`, emails `<email>`, URLs `<url>`, POSIX or Windows paths `<path>`, quoted strings `<str>`, and numbers `<num>`.
- **Tokenization**: single tokens by default; opt into bigrams with `--with-bigrams` for extra structure when false positives are low.
- **Streaming stats**: Laplace smoothing $k = 1.0$, *lazy* exponential decay (O(1) global scale) with default per-line factor `0.9999`, and vocab caps (~30k tokens / 10k templates) so memory stays flat.
- **Novelty score**: average token surprisal mapped to $[0,1)$ via $1 - e^{-S}$ for an intuitive rarity gauge.
- **Dynamic alerting**: constant-memory P² quantile estimator by default (no O(W log W) sorts). Supply `--window` to use the legacy rolling window quantile.
- **Modes / Profiles**: `--mode triage` ⇒ `q=0.992`; `--mode page` ⇒ `q=0.995`. Domain presets: `--profile web|k8s|auth` tune both window (when specified) and burn-in.
- **Guardrails**: line length truncated at `max_line_length` (default 2000 chars), tokens capped at `max_tokens_per_line` (default 400) to prevent pathological lines from skewing the model.
- **Operator presets**: `--profile web`, `--profile k8s`, `--profile auth` tune windows/quantiles; `--dedupe-template` suppresses repeat spam.

## How scoring works (plain English)

1. **Canonicalize**: mask volatile bits (timestamps, IDs, IPs, emails, URLs, file paths, quoted strings, numbers) so structurally similar lines collapse to the same template.
2. **Token frequencies**: keep a decayed count of every token (plus optional bigrams). Common words like `info` contribute little; rare words like `declined` carry many bits.
3. **Template rarity**: the masked template (e.g. `ERROR payment declined code=<num> user=<num>`) gets the same self-information treatment, rewarding surprising structures.
4. **Severity tap**: add a small, transparent bonus for WARN/ERROR levels.

The average token surprisal $S$ becomes a normalized novelty score via $1 - e^{-S}$ (bounded in $[0,1)$). Tail mode applies an adaptive quantile (P²) streaming estimator so thresholds track live distribution shifts without rescanning history.

### Decay (lazy)

Instead of scaling every count each decay step, Elaborlog maintains a *global scale factor* `g` and stores unscaled counts. Effective counts are `stored * g`. This makes decay O(1) per line and snapshot-friendly.

## Performance / Footprint

- Pure Python stdlib by default.
- Single pass, streaming-friendly.
- Exponential decay + LRU vocab caps keep the model fresh (no growing memory usage).
- Streaming P² quantile: constant memory, fast convergence after burn-in (see tests for statistical validation).
- Lazy decay: no vocabulary-wide scans; large vocabularies stay cheap.
- Guardrails: extreme line/token explosions capped early (tracked in snapshot counters).

## JSON Schemas

Machine-readable schemas:

- `schemas/alert.schema.json` (tail alerts JSONL)
- `schemas/rank.schema.json` (array output from `rank --json`)
- `schemas/explain.schema.json` (single object from `explain --json`)

Validate with `jsonschema` (installed via dev extras) or any Draft 2020-12 validator. Informal examples below:

Alert JSONL (tail):
```jsonc
{
	"timestamp": "2025-10-01T12:34:56Z",
	"level": "ERROR",
	"novelty": 0.873,
	"score": 12.45,
	"token_info_bits": 9.12,
	"template_info_bits": 3.02,
	"level_bonus": 0.70,
	"template": "ERROR payment declined code=<num> user=<num>",
	"template_probability": 0.00042,
	"tokens": ["error","payment","declined","code","402","user","9922"],
	"token_contributors": [ {"token":"declined","bits":4.3,"prob":0.05,"freq":1} ],
	"threshold": 0.861,
	"quantile": 0.992,
	"neighbors": [ {"similarity":0.62,"line":"ERROR payment failed code=500 user=9911"} ]
}
```

Rank JSON array (`--json`): list of similar objects minus threshold fields.

Explain JSON (`explain --json`): one object plus `weights`.

### Metrics Endpoint

The service exposes `GET /metrics` for observability and health dashboards.

Example (trimmed):
```jsonc
{
	"tokens": 18342,
	"templates": 6123,
	"total_tokens": 512340,
	"total_templates": 176540,
	"seen_lines": 176540,
	"g": 0.2243119,
	"renormalizations": 3,
	"truncated_lines": 12,
	"truncated_tokens": 4,
	"config": {
		"decay": 0.9999,
		"max_tokens": 30000,
		"max_templates": 10000
	}
}
```
Fields:
- `g`: current global decay scale factor (lazy decay internal state)
- `renormalizations`: how many times counts were rescaled to avoid underflow
- `truncated_lines` / `truncated_tokens`: guardrail activations
- `total_*` vs current `tokens`/`templates`: decayed vs distinct vocabulary sizes

Use this to alert when `renormalizations` spikes unexpectedly, or when vocabulary approaches caps (`max_tokens`, `max_templates`).

### Benchmark CI Job

A lightweight benchmark runs in CI (Python 3.11) and uploads `bench-result.json`. Treat early numbers as baselines; you can diff artifacts across commits to spot performance regressions.

### Performance Regression Guard

CI enforces a minimum throughput ratio vs. a committed baseline (`bench/baseline.json`). After each benchmark run we execute:

```
python scripts/check_benchmark.py --current bench-result.json --baseline bench/baseline.json --min-ratio 0.90
```

If current `lines_per_sec / baseline_lines_per_sec < 0.90`, the job fails, flagging a likely regression. Workflow for updating the baseline after an intentional improvement:

1. Run a representative local benchmark (repeat 3–5×, take median).
2. Edit `bench/baseline.json` with the new stable `lines_per_sec`.
3. Commit and open a PR (include rationale: hardware, command, median, variance).

Setting an initial baseline: the placeholder ships with `0` (always passes). Replace it once numbers stabilize on your primary CI runner.

Tune sensitivity by adjusting `--min-ratio` (e.g. `0.95` for stricter, `0.85` for looser) in `.github/workflows/ci.yml`.

### Static Type Checking

Mypy runs in CI with a moderately strict profile:

```
[tool.mypy]
disallow_untyped_defs = true
disallow_incomplete_defs = true
no_implicit_optional = true
warn_unused_ignores = true
warn_redundant_casts = true
strict_equality = true
```

Local invocation:

```
mypy src
```

Adding new modules? Prefer explicit return types. If a dynamic construct defies precise typing, isolate it and add a narrow `# type: ignore[code]` with justification.

### Schema Refactor Note

Schemas now employ `$defs` for `tokenContributor` and a timestamp pattern (subset RFC3339). Downstream generators can rely on stable contributor object shape.

## Roadmap

- Colorized/structured terminal output by default (optional rich).
- Windows Event Log reader and journalctl adapter.
- File globbing across rotated logs.
- Streaming clustering & online template evolution stats.
- Multi-source ingestion / metrics exporter.
- Optional approximate nearest-neighbor for large context windows.

## License

Apache-2.0

---

**Changelog**: see `CHANGELOG.md` for versioned feature history.
