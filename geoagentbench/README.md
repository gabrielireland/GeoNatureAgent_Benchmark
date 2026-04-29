# geoagentbench

Benchmarking framework for GeoNatureAgent — evaluates the geospatial AI agent against a structured set of test cases, scores results across multiple dimensions, and produces publication-ready metrics and visualisations.

---

## Quick Start

```bash
# Install (from repo root)
uv pip install -e ".[dev]"

# Smoke test — 6 dev cases, default model, output to ./results
python -m geoagentbench --cases dev

# Full paper benchmark (93 cases)
python -m geoagentbench --cases v5 --experiment benchmark/experiment.yaml --output-dir results/run_local
```

---

## CLI Reference

```
python -m geoagentbench [OPTIONS]

--experiment PATH          Path to experiment YAML config (see benchmark/experiment.yaml)
--cases SET                Case set to run: dev, v1, v2, v3, v4, v5, all (default: dev)
--case-file PATH           Run a custom cases JSON file instead of a named set
--model MODEL_ID           Override model from experiment YAML (e.g. claude-sonnet-4-20250514)
--prompt VERSION           Prompt version: v1, v2, v3 (default: v3)
--output-dir PATH          Output directory (default: ./results)
--filter-ids ID [ID ...]   Run only specific case IDs
--filter-categories C [C]  Run only cases in these categories
```

### Examples

```bash
# Run v5 (final paper benchmark) with a specific model
python -m geoagentbench --cases v5 --model vertex_ai/gemini-2.5-pro

# Debug a single failing case
python -m geoagentbench --cases v5 --filter-ids V5_21_comparison_lorca_murcia

# Run all comparison category cases
python -m geoagentbench --cases v5 --filter-categories comparison cross_indicator

# Point to a custom experiment config
python -m geoagentbench --experiment benchmark/experiments/exp_013_claude_opus46_vertex_v3.yaml --cases v3
```

---

## Case Sets

| Key | File | Cases | Purpose |
|-----|------|-------|---------|
| `dev` | dev.json | 6 | Smoke test — fast local iteration |
| `v1` | benchmark_v1.json | 20 | Original benchmark (migrated from tests/agent/) |
| `v2` | benchmark_v2.json | 8 | Extended v1 |
| `v3` | benchmark_v3.json | 30 | Province + municipality tasks |
| `v4` | benchmark_v4.json | 10 | Habitat cover tasks |
| **`v5`** | **benchmark_v5.json** | **93** | **Final paper benchmark — do not modify** |
| `all` | *(all files)* | 173+ | Combined, for exploratory runs only |

See `cases/README.md` for per-set category breakdown.

---

## Output Format

Each run produces three files in `{output-dir}/{experiment_id}/`:

```
{timestamp}_{experiment_id}.jsonl          # Per-case results (1 JSON object per line)
{timestamp}_{experiment_id}_summary.json   # Aggregated metrics for the run
benchmark_report.png                       # Visual overview (accuracy by category + difficulty)
```

### `results.jsonl` — Per-Case Fields

Each line is one case result:

| Field | Type | Description |
|-------|------|-------------|
| `case_id` | str | Case identifier |
| `passed` | bool | All checks passed |
| `error_category` | str | Failure reason (see categories below) |
| `rounds` | int | Agent loop iterations used |
| `tools_used` | list | Tool names called by the agent |
| `input_tokens` / `output_tokens` | int | Token counts |
| `cost_usd` | float | Estimated cost for this case |
| `duration_ms` | int | Wall-clock execution time |
| `check_score` | float | Fraction of checks passed (0.0–1.0) |
| `quality_check_score` | float | check_score weighted by check importance |
| `tool_f1` | float | F1 between expected and actual tool set |
| `keyword_coverage` | float | Fraction of must_contain keywords found |
| `rounds_utilization` | float | rounds / max_rounds |
| `cost_utilization` | float | cost_usd / max_cost_usd |
| `ms_per_round` | float | Latency per agent round |
| `answer_preview` | str | First 500 chars of the agent's answer |
| `checks` | list | Per-check pass/fail detail |
| `metadata` | dict | Raw agent trace, tool calls, actions |

### `_summary.json` — Aggregated Fields

```json
{
  "experiment_id": "exp_013_claude_opus46_vertex_v3",
  "model_id": "vertex_ai/claude-opus-4-6",
  "summary": {
    "total": 30,
    "passed": 14,
    "accuracy": 0.4667,
    "difficulty_weighted_accuracy": 0.459,
    "avg_check_score": 0.8383,
    "avg_quality_check_score": 0.7751
  },
  "totals": {
    "cost_usd": 0.6355,
    "input_tokens": 197412,
    "output_tokens": 38873,
    "duration_ms": 513001
  },
  "efficiency": {
    "avg_rounds_utilization": 0.387,
    "avg_cost_utilization": 0.161,
    "avg_tool_f1": 0.6474,
    "avg_keyword_coverage": 0.8276,
    "avg_ms_per_round": 8492.1
  },
  "accuracy_by_difficulty": { "easy": {...}, "medium": {...}, "hard": {...} },
  "check_type_accuracy": { "must_contain": 0.87, "expected_tools": 0.62, ... },
  "results": [...]
}
```

---

## Metrics

| Metric | Field | How to read |
|--------|-------|-------------|
| **Accuracy** | `summary.accuracy` | Fraction of cases where all checks passed |
| **Difficulty-weighted accuracy** | `summary.difficulty_weighted_accuracy` | easy=1×, medium=2×, hard=3× weights — penalises failing hard cases more |
| **Check score** | `avg_check_score` | Partial credit: fraction of individual checks passed (a case can fail overall but still score 0.8) |
| **Tool F1** | `avg_tool_f1` | Set F1 between expected and actual tools called — measures tool selection quality independently of the final answer |
| **Keyword coverage** | `avg_keyword_coverage` | Fraction of `must_contain` terms found in the answer — proxy for answer completeness |
| **Rounds utilisation** | `avg_rounds_utilization` | rounds_used / max_rounds — low values mean efficient agents; >1.0 means the agent hit the round cap |
| **Cost utilisation** | `avg_cost_utilization` | cost_usd / max_cost_usd — monitors budget headroom |
| **ms per round** | `avg_ms_per_round` | Latency efficiency — lower is faster per reasoning step |

### Error Categories

When a case fails, `error_category` explains why:

| Category | Meaning |
|----------|---------|
| `tool_missing` | Agent did not call one or more expected tools |
| `chart_missing` | Case required a chart but none was generated |
| `wrong_data` | Numeric answer outside ground truth tolerance |
| `rounds_exceeded` | Agent hit max_rounds without completing |
| `cost_exceeded` | Case cost exceeded max_cost_usd |
| `keyword_missing` | A required keyword was absent from the answer |
| `forbidden_keyword` | A must_not_contain term appeared in the answer |
| `latency_exceeded` | Execution exceeded the latency budget |
| `agent_error` | Agent crashed or returned an error |

---

## Experiment Config

Copy `benchmark/experiment.yaml` to `benchmark/experiments/exp_<id>_<description>.yaml` and edit:

```yaml
experiment_id: "exp_001_sonnet_zeroshot"
model:
  model_id: "claude-sonnet-4-20250514"   # or vertex_ai/gemini-2.5-pro, etc.
  max_tokens: 4096
agent:
  architecture: "single_agent"           # single_agent | multi_agent_planner_worker
  prompt_strategy: "zero_shot"           # zero_shot | chain_of_thought | few_shot
output:
  bucket: "gs://your-bucket/results"
  bq_dataset: "geoagentbench"
```

Credentials are injected by infrastructure — never put API keys in the YAML.

---

## Running on Cloud (CloudBuild)

```bash
# Edit cloudbuild-benchmark.yaml to point _EXPERIMENT_YAML at your config, then:
gcloud builds submit --config=GeoNatureAgent/cloudbuild-benchmark.yaml \
    --project=local-env-489816-i2
```

Results are uploaded to GCS and streamed to BigQuery automatically.

---

## Cross-Run Comparison

After multiple experiments, generate a leaderboard:

```bash
python -m geoagentbench.batch_summary --run-dir results/run_001
```

Produces `_batch_summary.json` + `leaderboard.png` — the paper's model comparison table.
