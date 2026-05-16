# How to Use GeoNatureAgent Benchmark

This guide explains how to use GeoNatureAgent Benchmark to evaluate your own LLM agent on environmental geospatial tasks.

---

## Architecture Overview

GeoNatureAgent Benchmark has three layers:

```
┌─────────────────────────────────────────┐
│  benchmark/experiments/exp_*.yaml       │  ← Experiment config (model, tasks, params)
├─────────────────────────────────────────┤
│  geoagentbench/                         │  ← Framework (runner, scoring, metrics)
│    runner.py      → orchestrates cases  │
│    scoring.py     → evaluates results   │
│    llm_client.py  → talks to LLM APIs   │
│    case_loader.py → loads task JSON     │
│    config.py      → parses YAML config  │
│    metrics.py     → cost calculation    │
├─────────────────────────────────────────┤
│  Your Agent                             │  ← The system under test
│    receives questions, calls tools,     │
│    returns structured output            │
└─────────────────────────────────────────┘
```

The runner sends each task's question to your agent, collects the output (answer, tools used, actions, token counts), and passes it to the scoring engine.

---

## Repository Layout

A folder-by-folder map of what ships with the repo and what each piece is for. Reading this once is enough to feel oriented before running anything.

### `api/` — the system under test (FastAPI service)

The agent's "world". Boots via `docker compose up` on `:8080` and exposes the endpoints the LLM calls through tools.

```
api/
├─ main.py              FastAPI app entry. Endpoints: /health, /agent/ask,
│                       /indicators, /cog/bounds, /admin/*, /tiles/*
├─ Dockerfile           python:3.11-slim + GDAL stack
├─ requirements.txt     Pinned API deps (fastapi, rasterio, anthropic, rio-tiler)
├─ active-layers.json   Layer catalog: id → COG path, type, year. Read by cache_manager
├─ cache_manager.py     Loads active-layers.json, opens COGs lazily
├─ admin_manager.py     Loads Spain/Portugal province + municipality GeoJSON
├─ rate_limiter.py      No-op stub in the OSS build
│
├─ agent/               Agent runtime — everything the LLM "sees"
│  ├─ agent.py             ReAct loop (model picks tool → executor runs → loop)
│  ├─ tools/
│  │   ├─ tools.json       JSON schemas the LLM receives
│  │   ├─ executors.py     Python implementation of each tool
│  │   └─ models.py        Pydantic argument/result types
│  ├─ prompts/
│  │   ├─ v1.md / v2.md    Historical prompts (NOT loaded by current code)
│  │   └─ v3.md            Production prompt (default, see AGENT_PROMPT_VERSION)
│  ├─ security.py          Input sanitizer + output identity scrub
│  ├─ session.py           In-memory multi-turn session store
│  ├─ provinces.py         Province lookup helper
│  ├─ charts.py            Bar/stacked-bar chart generation
│  ├─ event_logger.py      JSONL event log (no-op if log dir missing)
│  ├─ province_rankings.json         Pre-computed top-N rankings per indicator
│  ├─ province_rankings_prompt.txt   Prompt fragment listing rankings to the LLM
│  └─ data/                Compact JSON stats baked into the agent (CO2, fire, MFE)
│
├─ data/                Static geospatial data
│  ├─ cogs/                Raster COGs the agent reads — fetched via
│  │                       scripts/download_data.sh (see "Data files" below)
│  ├─ municipalities/      52 GeoJSONs (one per Spanish province)
│  ├─ spain_provinces.geojson, spain_ccaa.geojson, spain_admin_index.json
│  ├─ portugal_districts.json
│  └─ bigearthnet_portugal_stats.json   Pre-computed Portugal LULC stats
│
├─ endpoints/           Extra route module(s); currently just erosion.py
├─ services/            tile_tenant.py — passthrough access control in OSS build
└─ symbology/           Layer styling + legend gen, loaded from symbologies.json
```

### `geoagentbench/` — the examiner (Python package)

What you run to score an LLM. Invoked as `python -m geoagentbench --cases v5 --experiment <yaml>`.

```
geoagentbench/
├─ __main__.py          CLI entry (parses --cases, --experiment, --output-dir)
├─ runner.py            Per-experiment orchestration: case loop, LLM call, scoring
├─ llm_client.py        AnthropicClient (native) + LiteLLMClient (Vertex MaaS)
├─ scoring.py           The 8 check types (must_contain, expected_tools, …)
├─ metrics.py           Aggregation: per-seed mean+std, partial credit, tool F1
├─ case_loader.py       Resolves --cases name → JSON file
├─ config.py            Experiment YAML schema (pydantic)
├─ preflight.py         Validates config before running anything
├─ run_meta.py          Freezes config + env into _run_meta.json (provenance)
├─ batch_summary.py     Builds _batch_summary.json across experiments
├─ gcs_upload.py        Uploads results to GCS  (GCP-only, optional)
├─ bq_logger.py         Per-case rows → BigQuery     (GCP-only, optional)
├─ logging_structured.py
│
├─ cases/
│  ├─ benchmark_v5.json    The 93 evaluated cases
│  ├─ dev.json             Smoke-test subset for `--cases dev`
│  └─ README.md            Schema + category docs
└─ data/
   ├─ layers_registry.yaml   Human-readable layer catalog (docs only)
   └─ README.md
```

### `benchmark/` — what to evaluate

```
benchmark/
├─ experiment.yaml                       Schema reference / template
└─ experiments/
   ├─ exp_035_gemini25_pro_v5_seeds5.yaml      \
   ├─ exp_036_deepseek_v32_v5_seeds5.yaml       |
   ├─ exp_038_gpt_oss_120b_v5_seeds5.yaml       | One per evaluated model.
   ├─ exp_039_glm5_v5_seeds5.yaml               | These ARE the paper's runs.
   ├─ exp_040_qwen3_235b_v5_seeds5.yaml         |
   ├─ exp_041_llama4_scout_v5_seeds5.yaml       |
   ├─ exp_042_claude_sonnet4_v5_seeds5.yaml    /
   └─ archive/   14 legacy single-seed + rerun YAMLs (provenance only)
```

### `hf_dataset/` — Hugging Face export

```
hf_dataset/
├─ tasks.jsonl       93 cases in HF format
├─ results.jsonl     Per-seed per-model results
└─ README.md         Dataset card
```

### `scripts/` — utilities

```
scripts/
├─ download_data.sh           Fetches raster COGs → api/data/cogs/
├─ compile_final_results.py   GCS results → paper CSVs (single source of truth)
├─ prepare_hf_dataset.py      GCS + cases → hf_dataset/
├─ verify_package.py          Sanity check repo invariants
├─ visualize_benchmark.py     Plotting helpers
├─ compare_experiments.py     Diff two runs
├─ add_benchmark_case.py      Helper to add a case
└─ merge_rerun_results.py     [DEPRECATED] legacy _v5_rerun merge workflow
```

### Data files

Two raster COGs do **not** ship in the repo because of size (several hundred MB each):

| File | Indicator | Source |
|------|-----------|--------|
| `api/data/cogs/co2_spain.tif`     | `co2_spain_legislation`     | MITECO, processed by the authors |
| `api/data/cogs/gully_europe.tif`  | `rf_gully_probability`      | JRC LUCAS 2022 + random forest model |

`scripts/download_data.sh` is idempotent and supports two modes:

- **Automated**: set `CO2_SPAIN_URL` and `GULLY_EUROPE_URL` to public download URLs and re-run.
- **Manual**: place the files directly under `api/data/cogs/` and re-run to verify.

The script fails loudly (exit 1) with the exact missing-file list if neither is satisfied — the API will start without these files but tool calls targeting those two indicators will fail. See the script header for file specifications.

The third data file, `api/data/bigearthnet_portugal_stats.json`, ships in-repo and needs no download step.

---

## Quick Start

Two paths, pick whichever matches your infrastructure. They produce the same scientific output — the only difference is where things run.

- **Path A — Bring Your Own Infrastructure**: everything on a single machine (laptop, on-prem VM, any cloud). No Google Cloud account required.
- **Path B — Google Cloud**: parallel evaluation on Cloud Run Jobs, results streamed to GCS and BigQuery. This is how the paper's runs were produced.

### Path A — Bring Your Own Infrastructure

Single-machine setup. Anything that can run Docker and Python 3.11 works.

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
# (optional) set VERTEXAI_PROJECT if you'll evaluate Vertex MaaS models

# 2. Fetch the two raster COGs (see "Data files" above for source info)
CO2_SPAIN_URL=https://...      \
GULLY_EUROPE_URL=https://...   \
  ./scripts/download_data.sh
# OR: place co2_spain.tif and gully_europe.tif manually under api/data/cogs/
# then re-run ./scripts/download_data.sh to verify.

# 3. Start the API
docker compose up --build           # serves http://localhost:8080

# 4. In a separate shell, install the harness and run the benchmark
pip install -e .

# Smoke test (6 cases, ~$0.10):
python -m geoagentbench --cases dev --model claude-sonnet-4-20250514

# Full v5 benchmark (93 cases):
python -m geoagentbench \
  --cases v5 \
  --experiment benchmark/experiments/exp_042_claude_sonnet4_v5_seeds5.yaml \
  --output-dir results/
```

Results land locally under `results/`. No GCS upload, no BigQuery — `geoagentbench/gcs_upload.py` and `bq_logger.py` are skipped when the relevant env vars are unset.

To evaluate a Vertex MaaS model (Gemini, Llama 4 Scout, etc.), set `VERTEXAI_PROJECT` and `VERTEXAI_LOCATION` in `.env`, authenticate with `gcloud auth application-default login`, and point `--experiment` at one of the `vertex_ai/` experiment YAMLs. The harness reads the same YAMLs whether you run locally or on Cloud Run.

### Path B — Google Cloud (Cloud Build + Cloud Run Jobs)

How the paper's runs were produced. You need a GCP project with Cloud Build, Cloud Run, GCS, Artifact Registry, and optionally BigQuery enabled.

```bash
# 1. One-time GCP setup
#    - Create a GCS bucket for results       (e.g. geonature-agent-results)
#    - Create an Artifact Registry repo      (e.g. agent-images)
#    - Create a service account with roles: Cloud Run Admin, Storage Admin,
#      BigQuery Data Editor (if streaming), Vertex AI User (for MaaS models)
#    - Store the Anthropic API key in Secret Manager as ANTHROPIC_KEY_1

# 2. Edit cloudbuild-benchmark.yaml
#    Replace all YOUR_GCP_PROJECT_ID placeholders with your project id.
#    Set _EXPERIMENT_YAMLS to a comma-separated list of YAMLs to run.
#    Set _BUCKET to your results bucket and _AR_REGION/_AR_REPO accordingly.

# 3. Submit the build
gcloud builds submit \
  --config=cloudbuild-benchmark.yaml \
  --project=YOUR_GCP_PROJECT_ID
```

Cloud Build builds the API image, deploys a Cloud Run Job that runs every experiment in `_EXPERIMENT_YAMLS` sequentially, and writes:

- `gs://_BUCKET/<run-prefix>/<exp_id>/results.jsonl` — per-case results
- `gs://_BUCKET/<run-prefix>/<exp_id>/_run_meta.json` — frozen config + environment
- `gs://_BUCKET/<run-prefix>/_batch_summary.json` — cross-experiment summary
- BigQuery rows (if `BQ_LOG_TABLE` is set in the job env)

After the run completes, pull the results down and regenerate the paper artifacts:

```bash
python scripts/compile_final_results.py    # GCS results → paper/final_results/*.csv
```

`cloudbuild-benchmark.yaml` is heavily commented — edit it directly rather than passing `--substitutions=` on the command line.

---

## Evaluate Your Own Agent

To benchmark a custom agent, you need to integrate it with the runner. The runner expects your agent to:

1. Accept a natural language question
2. Have access to the 12 geospatial tools (via MCP or direct API)
3. Return a structured output dict

### Agent Output Contract

Your agent's `run_agent()` function must return a dict with these fields:

```python
{
    "answer": str,          # The agent's final text response
    "full_answer": str,     # Complete response (may include reasoning)
    "tools_used": [         # List of tools called
        {"tool": "analyze_area", "input": {...}, "output": {...}},
        {"tool": "lookup_municipality", "input": {...}, "output": {...}},
    ],
    "actions": [            # Frontend actions triggered
        {"type": "fly_to_bounds", ...},
    ],
    "usage": {
        "input_tokens": int,
        "output_tokens": int,
        "rounds": int,      # Number of agent loop iterations
    },
    "chart_urls": [],       # URLs of generated charts (if any)
    "conversation_trace": [],  # Full LLM conversation (optional, for debugging)
}
```

### Integration Option 1: Modify the Runner

Edit `geoagentbench/runner.py` — replace the `_run_case_in_process` function to call your agent:

```python
def _run_case_in_process(conn, case, model_id, client_kwargs):
    try:
        from your_agent import run_agent  # <-- your agent

        result = run_agent(
            question=case["question"],
            session_history=case.get("session_history"),
        )
        conn.send(("ok", result))
    except Exception as exc:
        conn.send(("error", str(exc)))
    finally:
        conn.close()
```

### Integration Option 2: Run Offline and Score Separately

If your agent runs separately, collect results as JSONL (one line per case) and use the scoring engine directly:

```python
import json
from geoagentbench.case_loader import load_cases
from geoagentbench.scoring import score_result
from geoagentbench.metrics import compute_cost

cases = load_cases(case_set="v5")
case_map = {c["id"]: c for c in cases}

with open("my_agent_results.jsonl") as f:
    for line in f:
        agent_output = json.loads(line)
        case = case_map[agent_output["case_id"]]

        scored = score_result(
            case=case,
            agent_output=agent_output,
            duration_ms=agent_output.get("duration_ms", 0),
            cost_usd=agent_output.get("cost_usd", 0.0),
        )
        print(f"{scored.case_id}: {'PASS' if scored.passed else 'FAIL'} "
              f"(check_score={scored.check_score}, tool_f1={scored.tool_f1})")
```

---

## The 12 Geospatial Tools

Your agent must have access to these tools via MCP or equivalent:

| Tool | Purpose | Example Input |
|------|---------|---------------|
| `list_layers` | List available map layers | `{}` |
| `get_legend` | Get legend for a layer | `{"layer": "co2_spain_legislation"}` |
| `analyze_area` | Zonal statistics for a geometry | `{"layer": "rf_gully_probability", "province": "Murcia"}` |
| `get_layer_bounds` | Get spatial extent of a layer | `{"layer": "co2_spain_legislation"}` |
| `lookup_province` | Get province geometry by name | `{"name": "Navarra"}` |
| `lookup_municipality` | Get municipality geometry | `{"name": "Lorca", "province": "Murcia"}` |
| `compare_areas` | Compare two areas | `{"layer": "co2_spain_legislation", "area1": "Murcia", "area2": "Cordoba"}` |
| `find_top_n` | Rank provinces by indicator | `{"layer": "rf_gully_probability", "n": 5, "order": "desc"}` |
| `generate_chart` | Create a chart | `{"type": "bar", "data": [...]}` |
| `analyze_multi_layer` | Analyze multiple layers | `{"layers": [...], "province": "Murcia"}` |
| `toggle_layer` | Toggle layer visibility | `{"layer": "burnt_areas", "visible": true}` |
| `reject_task` | Explicitly refuse an invalid task | `{"reason": "No data available for this country"}` |

---

## Understanding the Scoring

Each case has multiple checks. A case **passes** only when ALL checks pass.

### Check Types

| Check | What it measures | How it works |
|-------|-----------------|-------------|
| `expected_tools` | Did the agent call the right tools? | Set F1 between expected and actual tools |
| `expected_actions` | Did the agent trigger the right UI actions? | Set F1 |
| `must_contain` | Does the answer include required keywords? | Substring match (case-insensitive) |
| `must_not_contain` | Does the answer avoid forbidden terms? | Absence check |
| `ground_truth` | Are numeric values correct? | Within tolerance (e.g. 64.6% +/- 3%) |
| `chart_generated` | Was a chart produced? | Checks chart_urls list |
| `max_rounds` | Did the agent stay within round budget? | rounds <= max_rounds |
| `max_cost_usd` | Did the agent stay within cost budget? | cost <= max_cost |

### Metrics

| Metric | Range | What it means |
|--------|-------|---------------|
| **Accuracy** | 0-100% | Fraction of cases where ALL checks pass |
| **Check score** | 0.0-1.0 | Partial credit: fraction of individual checks passed per case |
| **Tool F1** | 0.0-1.0 | How well the agent selected the right tools |
| **Keyword coverage** | 0.0-1.0 | Fraction of required keywords found in the answer |
| **Cost/case** | $ | Average cost per task |

### Error Categories

When a case fails, the scoring engine assigns an error category based on the first failing check:

```
tool_missing      → Agent didn't call a required tool
chart_missing     → Chart was expected but not generated
wrong_data        → Numeric answer outside tolerance
rounds_exceeded   → Hit the round cap
cost_exceeded     → Exceeded cost budget
keyword_missing   → A required keyword was absent
forbidden_keyword → A forbidden term appeared
agent_error       → Agent crashed or returned an error
```

---

## Adding Custom Tasks

### Task JSON Schema

```json
{
  "id": "CUSTOM_01_my_task",
  "category": "single_analysis",
  "difficulty": "medium",
  "description": "What this task tests",
  "question": "The natural language prompt sent to the agent",
  "expected_tools": ["lookup_province", "analyze_area"],
  "expected_actions": ["fly_to_bounds"],
  "must_contain": ["Navarra", "%"],
  "must_not_contain": ["error"],
  "max_rounds": 4,
  "max_cost_usd": 0.10,
  "ground_truth": [
    {"label": "Navarra", "expected_pct": 64.6, "tolerance": 3.0}
  ],
  "ground_truth_notes": "Explanation of expected behavior"
}
```

### Adding tasks interactively

```bash
python scripts/add_benchmark_case.py --target v5
```

### Running a custom task file

```bash
python -m geoagentbench --case-file my_tasks.json
```

---

## Experiment Configuration

Each experiment is a YAML file:

```yaml
experiment_id: "my_experiment_001"
description: "Testing my custom agent"

model:
  model_id: "claude-sonnet-4-20250514"  # or vertex_ai/gemini-2.5-pro
  max_tokens: 4096

sampling:
  temperature: 1.0

agent:
  architecture: single_agent
  prompt_strategy: zero_shot
  prompt_version: v3
  max_turns: 10

tasks:
  case_set: v5              # dev, v5, or all
  # categories: [municipality, ranking]  # optional filter
  # ids: [V5_01, V5_02]                 # optional filter

output:
  prefix: "GeoNatureAgent/experiments"
  bucket: "my-gcs-bucket"   # optional: upload results to GCS
```

Run with:
```bash
python -m geoagentbench --experiment benchmark/experiments/my_experiment.yaml
```

---

## Output Files

Each run produces:

```
results/{experiment_id}/
├── {timestamp}_{experiment_id}.jsonl       # Per-case results (1 JSON per line)
├── {timestamp}_{experiment_id}_summary.json # Aggregated metrics
├── benchmark_report.png                     # Visual summary
└── experiment.yaml                          # Frozen copy of config used
```

### Reading Results Programmatically

```python
import json

# Per-case results
with open("results/my_experiment/20260425_120000_my_experiment.jsonl") as f:
    results = [json.loads(line) for line in f]

# Summary
for r in results:
    print(f"{r['case_id']}: {'PASS' if r['passed'] else 'FAIL'} "
          f"({r['check_score']:.0%} checks, ${r['cost_usd']:.4f})")

# Aggregate
passed = sum(r["passed"] for r in results)
print(f"\nAccuracy: {passed}/{len(results)} = {passed/len(results):.1%}")
```

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| All cases fail with `agent_error` | QGIS/MCP server not running | Start QGIS + MCP before running |
| `tool_missing` on every case | Agent not configured with tool definitions | Ensure tools are registered in the system prompt |
| `keyword_missing` failures | Agent answers in wrong language | Check `language` category cases; ensure agent responds in the question's language |
| Token/cost accounting is zero | LLM client not reporting usage | Check that your client returns `usage.input_tokens` and `usage.output_tokens` |
| `forbidden_keyword` failures | Agent says "error" or "not found" | These keywords indicate hallucination — the agent should gracefully handle missing data |

---

## Extending GeoNatureAgent Benchmark

### Adding a new LLM backend

Implement the `BaseLLMClient` interface in `geoagentbench/llm_client.py`:

```python
class MyCustomClient(BaseLLMClient):
    def __init__(self, model_id: str, **kwargs):
        self.model_id = model_id

    def create_message(self, system, messages, tools, max_tokens=2048):
        # Call your LLM API
        # Return an LLMResponse with content, token counts, etc.
        return LLMResponse(
            content=[_TextBlock(text="...")],
            stop_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
            model=self.model_id,
            latency_ms=500,
        )
```

Then update the `create_client()` factory to route to your backend.

### Adding new tools

Add tool definitions to the agent's system prompt and implement the tool handler. The scoring engine only checks tool **names** (not inputs/outputs), so as long as your tool is called with the expected name, it will be scored correctly.

### Adding new indicators / geographies

1. Add the raster data to your geospatial API
2. Create task JSON with the new indicator/geography
3. Set appropriate ground truth and keywords
4. Run and validate

The framework is geography-agnostic — tasks just need questions, expected tools, and validation criteria.
