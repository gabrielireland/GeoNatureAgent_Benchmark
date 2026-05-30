# GeoNatureAgent Benchmark Dataset

Benchmark tasks and evaluation results from **GeoNatureAgent Benchmark: Benchmarking LLM Agents for Environmental Geospatial Analysis**.

## Files

| File | Records | Description |
|------|---------|-------------|
| `tasks.jsonl` | 93 | Benchmark task definitions (18 categories, 3 difficulty levels) |
| `results.jsonl` | 1860 | Per-case evaluation results for the 7 final models across seeds (93 tasks × 3 seeds for six models, × 2 samples for Claude Sonnet 4) |

> **Provenance:** `results.jsonl` is regenerated from the canonical per-case matrix
> (`paper/final_results/per_case.csv`), which is compiled from the final `*_v5_seeds5`
> Cloud Run experiments listed in `paper/final_results/sources.yaml`. It reproduces the
> paper leaderboard exactly. Earlier single-seed / exploratory runs (and discontinued
> models such as Llama 4 Maverick) are **not** included here.

## Task Schema (`tasks.jsonl`)

Each line is a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique task identifier (e.g. `V5_01_municipality_co2_lorca`) |
| `category` | string | One of 18 categories |
| `difficulty` | string | `easy`, `medium`, or `hard` |
| `description` | string | What the task tests |
| `question` | string | Natural language prompt sent to the agent |
| `expected_tools` | list[str] | Tools the agent should call |
| `expected_actions` | list[str] | UI actions expected |
| `must_contain` | list[str] | Keywords required in the answer |
| `must_not_contain` | list[str] | Keywords that must not appear |
| `max_rounds` | int | Maximum agent loop iterations |
| `max_cost_usd` | float | Cost budget per task |
| `ground_truth_notes` | string | Human explanation of expected behavior |

## Result Schema (`results.jsonl`)

Each line is one (model × case × seed) evaluation:

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | string | Model name (e.g. `Claude Sonnet 4`, `DeepSeek V3.2`) |
| `experiment_id` | string | Cloud Run experiment identifier (`*_v5_seeds5`) |
| `case_id` | string | Task ID |
| `seed` | int | Random seed (`42`, `1337`, `2024`; Claude has two samples, no seed param) |
| `category` | string | Task category |
| `passed` | bool | All applicable capability checks passed (cost gate excluded) |
| `passed_with_cost_gate` | bool | `passed` AND within the per-case cost budget |
| `check_score` | float | Fraction of individual checks passed (0.0–1.0) |
| `keyword_coverage` | float | Fraction of `must_contain` keywords found |
| `cost_usd` | float | Estimated per-case cost |
| `input_tokens` / `output_tokens` | int | Token counts |
| `rounds` | int | Agent loop iterations used |
| `duration_ms` | int | Wall-clock time |
| `error_category` | string | First failing check (null if passed) |

> Per-case `tool_f1` and the exact `tools_used` lists are not carried in the compiled
> matrix; they are available in the full conversation traces archived with the dataset
> record (see Citation / Zenodo).

## Categories

| Category | Tasks | Description |
|----------|-------|-------------|
| comparison | 2 | Province pair comparison |
| cross_indicator | 8 | Multi-indicator reasoning (CO2 + erosion + land cover) |
| deep_dive | 6 | Full multi-indicator profile + chart |
| error_handling | 6 | Hallucination prevention |
| error_recovery | 3 | Graceful fallback |
| habitat_analysis | 7 | BigEarthNet V2 land cover (Portugal) |
| interpretation | 7 | Policy reasoning from data |
| language | 6 | Galician, Basque inputs |
| memory | 6 | Multi-turn recall |
| multi_municipality_ranking | 3 | Rank municipalities |
| municipality | 4 | Municipality-level analysis |
| province_aggregation | 2 | CCAA-level aggregation |
| ranking | 2 | Top-N queries |
| single_analysis | 2 | Basic single-province queries |
| spatial_reasoning | 4 | Geographic knowledge |
| temporal_change | 1 | Cross-country temporal context |
| threshold | 3 | Numeric threshold filtering |
| tool_selection | 21 | Chart type, multi-layer toggle |

## Models Evaluated (final leaderboard)

| Model | Accuracy | Cost/case |
|-------|----------|-----------|
| Claude Sonnet 4 | 60.8% | $0.127 |
| DeepSeek V3.2 | 56.3% | $0.011 |
| GLM-5 | 50.2% | $0.038 |
| Gemini 2.5 Pro | 48.0% | $0.052 |
| Qwen3-235B | 41.2% | $0.010 |
| GPT-OSS-120B | 34.1% | $0.089 |
| Llama 4 Scout | 26.9% | $0.003 |

## Usage

```python
import json
from collections import defaultdict

tasks = [json.loads(line) for line in open("tasks.jsonl")]
print(f"{len(tasks)} tasks, {len(set(t['category'] for t in tasks))} categories")

results = [json.loads(line) for line in open("results.jsonl")]
acc = defaultdict(list)
for r in results:
    acc[r["model_id"]].append(r["passed"])
for model in sorted(acc, key=lambda m: -sum(acc[m]) / len(acc[m])):
    print(f"{model}: {sum(acc[model]) / len(acc[model]):.1%}")
```

## Citation

```bibtex
@article{diazireland2026geoagentbench,
  title   = {GeoNatureAgent Benchmark: Benchmarking LLM Agents for Environmental Geospatial Analysis},
  author  = {Diaz-Ireland, Gabriel and Prieto-Herr{\'a}ez, Diego and Garc{\'i}a Peces, Mario and Vel{\'a}zquez, Javier and Jain, Devika},
  year    = {2026},
  url     = {https://github.com/gabrielireland/GeoNatureAgent_Benchmark}
}
```

## License

Apache 2.0
