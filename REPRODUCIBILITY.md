# Reproducing GeoAgentBench Results

This guide covers end-to-end reproduction: from running the benchmark to generating paper figures.

---

## 1. Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- GCP project with Vertex AI enabled (for Vertex models)
- Anthropic API key (for Claude models)
- QGIS + MCP server (for live benchmark runs)

```bash
git clone https://github.com/darwin-geo/GeoNatureAgent.git
cd GeoNatureAgent
git submodule update --init --recursive
uv pip install -e ".[dev]"
```

---

## 2. Benchmark Design

### Task definitions

All 93 tasks are defined in `geoagentbench/cases/benchmark_v5.json`. Each task specifies:
- A natural language question
- Expected tools and actions
- Required/forbidden keywords
- Round and cost budgets
- Ground truth (where applicable)

See `geoagentbench/cases/README.md` for the full category breakdown.

### Scoring

`geoagentbench/scoring.py` evaluates each task across 8 check types:
1. **expected_tools** — Tool F1 between expected and actual
2. **expected_actions** — Action F1
3. **must_contain** — Keyword coverage
4. **must_not_contain** — Forbidden keyword check
5. **ground_truth** — Numeric accuracy within tolerance
6. **chart_generated** — Chart presence when required
7. **max_rounds** — Round budget compliance
8. **max_cost_usd** — Cost budget compliance

A task passes only when ALL checks pass. Partial credit (check_score) captures per-check granularity.

---

## 3. Experiment Configurations

Each model has a dedicated experiment YAML in `benchmark/experiments/`:

| Experiment | Model | Access |
|-----------|-------|--------|
| `exp_035_gemini25_pro_v5.yaml` | Gemini 2.5 Pro | Vertex AI native |
| `exp_036_deepseek_v32_v5.yaml` | DeepSeek V3.2 | Vertex AI MaaS |
| `exp_037_llama4_maverick_v5.yaml` | Llama 4 Maverick | Vertex AI MaaS |
| `exp_038_gpt_oss_120b_v5.yaml` | GPT-OSS-120B | Vertex AI MaaS |
| `exp_039_glm5_v5.yaml` | GLM-5 | Vertex AI MaaS |
| `exp_040_qwen3_235b_v5.yaml` | Qwen3-235B | Vertex AI MaaS |
| `exp_041_llama4_scout_v5.yaml` | Llama 4 Scout | Vertex AI MaaS |
| `exp_042_claude_sonnet4_v5.yaml` | Claude Sonnet 4 | Anthropic API |

All experiments use:
- `case_set: v5` (93 tasks)
- `architecture: single_agent`
- `prompt_strategy: zero_shot`
- `prompt_version: v3`
- `max_turns: 10`

---

## 4. Running the Benchmark

### Local (single model)

```bash
# Dev smoke test (6 cases)
python -m geoagentbench --cases dev

# Full v5 benchmark with default model
python -m geoagentbench --cases v5 --output-dir results/

# Specific model
python -m geoagentbench --cases v5 --model vertex_ai/zai-org/glm-5-maas

# Filter by category
python -m geoagentbench --cases v5 --filter-categories error_handling threshold
```

### Cloud (multi-model batch)

The Cloud Build pipeline runs multiple experiments in sequence on a GCE VM with QGIS + MCP:

1. Edit `cloudbuild-benchmark.yaml`:
   - Set `_EXPERIMENT_YAMLS` to comma-separated experiment paths
   - Set `_BUCKET` for results storage
2. Submit:
   ```bash
   gcloud builds submit --config=cloudbuild-benchmark.yaml
   ```

Results are uploaded to GCS: `gs://<bucket>/GeoNatureAgent/experiments/run_<timestamp>/<experiment_id>/`

Each experiment produces:
- `results.jsonl` — per-case results (1 line per task)
- `_run_meta.json` — experiment metadata
- `experiment.yaml` — copy of the config used
- `benchmark_report.png` — visual summary

Batch-level artifacts (at the run root):
- `_batch_summary.json` — leaderboard data
- `leaderboard.png` — cross-model comparison chart

---

## 5. Results Locations

### Paper results (GCS)

| Run | Models | Location |
|-----|--------|----------|
| Original (6 models) | exp_035--040 | `gs://geonature-agent-results/.../run_20260422_224005/` |
| Re-run (2 models) | exp_041--042 | `gs://geonature-agent-results/.../run_20260424_053232/` |

### Local copy

For figure generation, results are expected at `/tmp/geoagentbench_v5_results/`:

```bash
# Download from GCS
mkdir -p /tmp/geoagentbench_v5_results
for exp in exp_035 exp_036 exp_037 exp_038 exp_039 exp_040; do
  gsutil cp "gs://geonature-agent-results/GeoNatureAgent/experiments/run_20260422_224005/${exp}_*_v5/results.jsonl" \
    "/tmp/geoagentbench_v5_results/${exp}_*_v5.jsonl"
done
for exp in exp_041 exp_042; do
  gsutil cp "gs://geonature-agent-results/GeoNatureAgent/experiments/run_20260424_053232/${exp}_*_v5/results.jsonl" \
    "/tmp/geoagentbench_v5_results/${exp}_*_v5.jsonl"
done
```

---

## 6. Generating Paper Figures

All 8 figures are generated from a single script:

```bash
python agentic_documentation/paper/generate_figures.py
```

Output: `agentic_documentation/paper/figures/fig{1..8}_*.{pdf,png}`

| Figure | Content |
|--------|---------|
| fig1 | Leaderboard (accuracy bar chart) |
| fig2 | Cost-accuracy trade-off (bubble chart) |
| fig3 | Binary vs partial credit comparison |
| fig4 | Category heatmap (model x category) |
| fig5 | Hard cases analysis |
| fig6 | Architecture diagram |
| fig7 | Tokens vs accuracy |
| fig8 | Scoring pipeline |

---

## 7. Compiling the Paper

```bash
cd agentic_documentation/paper
pdflatex geoagentbench.tex
bibtex geoagentbench
pdflatex geoagentbench.tex
pdflatex geoagentbench.tex
```

---

## 8. Preparing the HuggingFace Dataset

```bash
python scripts/prepare_hf_dataset.py --results-dir /tmp/geoagentbench_v5_results
```

Generates `hf_dataset/tasks.jsonl` (93 tasks) and `hf_dataset/results.jsonl` (744 results).

---

## 9. Verification

Run the package verification script to check all artifacts are consistent:

```bash
python scripts/verify_package.py --results-dir /tmp/geoagentbench_v5_results
```

This checks: case counts, category counts, result record counts, accuracy matches paper Table 4, no stale references in READMEs, no TODOs in paper, all citations resolved, all figures exist, LICENSE and CITATION.cff exist, and HF dataset integrity.

Expected output: `ALL CHECKS PASSED` (35 checks).
