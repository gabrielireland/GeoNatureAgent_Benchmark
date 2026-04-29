# GeoAgentBench Dataset

Benchmark tasks and evaluation results from **GeoAgentBench: Benchmarking LLM Agents for Environmental Geospatial Analysis**.

## Files

| File | Records | Description |
|------|---------|-------------|
| `tasks.jsonl` | 93 | Benchmark task definitions (18 categories, 3 difficulty levels) |
| `results.jsonl` | 744 | Evaluation results (93 tasks x 8 models) |

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

Each line is a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | string | Model name (e.g. `glm-5`, `claude-sonnet-4`) |
| `experiment_id` | string | Experiment identifier |
| `case_id` | string | Task ID |
| `passed` | bool | All checks passed |
| `error_category` | string | Failure reason (null if passed) |
| `rounds` | int | Agent loop iterations used |
| `tools_used` | list[str] | Tools actually called |
| `input_tokens` | int | Input token count |
| `output_tokens` | int | Output token count |
| `cost_usd` | float | Estimated cost |
| `duration_ms` | int | Wall-clock time |
| `check_score` | float | Fraction of checks passed (0.0--1.0) |
| `tool_f1` | float | F1 between expected and actual tools |
| `keyword_coverage` | float | Fraction of must_contain keywords found |

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

## Models Evaluated

| Model | Accuracy | Cost/case |
|-------|----------|-----------|
| GLM-5 | 58.1% | $0.027 |
| Claude Sonnet 4 | 58.1% | $0.087 |
| DeepSeek V3.2 | 52.7% | $0.008 |
| Qwen3-235B | 47.3% | $0.005 |
| Gemini 2.5 Pro | 39.8% | $0.032 |
| GPT-OSS-120B | 39.8% | $0.051 |
| Llama 4 Scout | 5.4% | $0.000 |
| Llama 4 Maverick | 0.0% | --- |

## Usage

```python
import json

# Load tasks
tasks = [json.loads(line) for line in open("tasks.jsonl")]
print(f"{len(tasks)} tasks, {len(set(t['category'] for t in tasks))} categories")

# Load results
results = [json.loads(line) for line in open("results.jsonl")]
# Accuracy per model
from collections import Counter
for model in sorted(set(r["model_id"] for r in results)):
    model_results = [r for r in results if r["model_id"] == model]
    acc = sum(r["passed"] for r in model_results) / len(model_results)
    print(f"{model}: {acc:.1%}")
```

## Citation

```bibtex
@article{diazireland2026geoagentbench,
  title   = {GeoAgentBench: Benchmarking LLM Agents for Environmental Geospatial Analysis},
  author  = {Diaz-Ireland, Gabriel and Prieto-Herr{\'a}ez, Diego and Vel{\'a}zquez, Javier and Garc{\'i}a Peces, Mario and Perez, Guillermo},
  year    = {2026},
  url     = {https://github.com/darwin-geo/GeoNatureAgent}
}
```

## License

Apache 2.0
