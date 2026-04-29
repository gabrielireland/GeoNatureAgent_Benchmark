# How to Use GeoAgentBench

This guide explains how to use GeoAgentBench to evaluate your own LLM agent on environmental geospatial tasks.

---

## Architecture Overview

GeoAgentBench has three layers:

```
┌─────────────────────────────────────────┐
│  benchmark/experiments/exp_*.yaml       │  ← Experiment config (model, tasks, params)
├─────────────────────────────────────────┤
│  geoagentbench/                         │  ← Framework (runner, scoring, metrics)
│    runner.py      → orchestrates cases  │
│    scoring.py     → evaluates results   │
│    llm_client.py  → talks to LLM APIs   │
│    case_loader.py → loads task JSON      │
│    config.py      → parses YAML config  │
│    metrics.py     → cost calculation     │
├─────────────────────────────────────────┤
│  Your Agent                             │  ← The system under test
│    receives questions, calls tools,     │
│    returns structured output            │
└─────────────────────────────────────────┘
```

The runner sends each task's question to your agent, collects the output (answer, tools used, actions, token counts), and passes it to the scoring engine.

---

## Quick Start: Evaluate an Existing Model

If you just want to benchmark a model that GeoAgentBench already supports (Anthropic or Vertex AI models):

```bash
# Install
pip install -e .

# Run 6 dev cases with Claude Sonnet 4
export ANTHROPIC_API_KEY=sk-...
python -m geoagentbench --cases dev --model claude-sonnet-4-20250514

# Run 6 dev cases with Gemini via Vertex AI
export VERTEXAI_PROJECT=your-project
export VERTEXAI_LOCATION=us-central1
python -m geoagentbench --cases dev --model vertex_ai/gemini-2.5-pro

# Full v5 benchmark (93 cases)
python -m geoagentbench --cases v5 --model vertex_ai/zai-org/glm-5-maas
```

**Important**: The benchmark requires a running geospatial API (QGIS + MCP server) to execute tool calls. Without it, all tool-dependent cases will fail. The Cloud Build pipeline (`cloudbuild-benchmark.yaml` in the parent repo) automates this infrastructure.

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

## Extending GeoAgentBench

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
