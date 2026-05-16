# Reproducing GeoNatureAgent Benchmark Results

This guide covers end-to-end reproduction: from running the benchmark to generating paper figures.

---

## 1. Prerequisites

- Python 3.10+
- Docker + Docker Compose (for the local self-hosted API)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- GCP project with Vertex AI enabled (for Vertex models)
- Anthropic API key (for Claude models)

There is **no centrally-hosted public API** — the open-source release ships the FastAPI service under `api/` so anyone can run it locally.

```bash
git clone https://github.com/gabrielireland/GeoNatureAgent_Benchmark.git
cd GeoNatureAgent_Benchmark
uv pip install -e ".[dev]"

# Fetch the 3 data files (CO2 Spain COG, gully Europe COG, BigEarthNet Portugal JSON)
./scripts/download_data.sh

# Start the API locally on port 8080
export ANTHROPIC_API_KEY=sk-...
docker compose up --build -d
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

Each of the 7 evaluated models has a dedicated experiment YAML in `benchmark/experiments/`:

| Experiment | Model | Access |
|-----------|-------|--------|
| `exp_035_gemini25_pro_v5.yaml` | Gemini 2.5 Pro | Vertex AI native |
| `exp_036_deepseek_v32_v5.yaml` | DeepSeek V3.2 | Vertex AI MaaS |
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
- `temperature: 1.0`

### Multi-seed re-runs

To reproduce the variance reported in the paper, the same 8 models have **3-seed** counterparts at `benchmark/experiments/exp_NNN_*_v5_seeds5.yaml`. Each carries `sampling.seeds: [42, 1337, 2024]` and produces three independent runs per (model, case) pair. The runner records `seed` and `seed_run_id` on every result line in `results.jsonl`.

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

The benchmark also supports parallel Cloud Run Job execution for batched multi-model runs via the Cloud Build pipeline at `cloudbuild-benchmark.yaml` — adapt the substitution variables in that file to your own GCP project. For local-only runs, use the Docker container directly:

```bash
# Single experiment locally
docker compose run --rm api python -m geoagentbench \
  --experiment benchmark/experiments/exp_042_claude_sonnet4_v5_seeds5.yaml \
  --output-dir results/exp_042_seeds3
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

Final paper numbers are aggregated from per-model 3-seed runs of the v5 case set. The authoritative manifest mapping each model to its Cloud Run output directory lives at:

```
paper/final_results/sources.yaml
```

Each entry pins a model's leaderboard cell to:
- `experiment_id` — the `_seeds5` YAML run
- `run_dir` — the dated folder under `gs://geonature-agent-results/GeoNatureAgent/experiments/`
- `cloudbuild_id` — the Cloud Build ID that produced it (for tracing back to logs)

To pull every results file locally:

```bash
mkdir -p /tmp/geoagentbench_v5_results
python -c "
import yaml, subprocess
cfg = yaml.safe_load(open('paper/final_results/sources.yaml'))
for name, spec in cfg['models'].items():
    src = f\"gs://{cfg['bucket']}/GeoNatureAgent/experiments/{spec['run_dir']}/{spec['experiment_id']}/results.jsonl\"
    dst = f\"/tmp/geoagentbench_v5_results/{spec['experiment_id']}.jsonl\"
    subprocess.run(['gsutil', 'cp', src, dst], check=True)
"
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
cd paper
pdflatex geonatureagent_benchmark.tex
bibtex geonatureagent_benchmark
pdflatex geonatureagent_benchmark.tex
pdflatex geonatureagent_benchmark.tex
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

---

## 10. Final Results Compilation

Every number reported in the paper is produced from raw GCS results by a single deterministic script. This section documents the inputs, the method, and the replay command so that any reviewer can verify reproducibility without re-running the benchmark.

### Provenance

The source-of-truth manifest is `paper/final_results/sources.yaml`. It maps each model's leaderboard cell to a specific Cloud Run output directory and Cloud Build ID:

```yaml
bucket: geonature-agent-results
models:
  Gemini 2.5 Pro:
    experiment_id: exp_035_gemini25_pro_v5_seeds5
    run_dir:       run_20260512_205246
    cloudbuild_id: 87d411f7-8328-456f-b350-e3f334172eb6
  # ... one block per model
```

Each `run_dir` contains a `results.jsonl` with one row per (case, seed) observation — i.e. 93 × 3 = 279 rows per model. Every row carries its own `seed`, `case_id`, `experiment_id`, `git_commit`, and `model_id`, so individual rows can be traced back to a Cloud Build log line.

### Aggregation method

For each model, we report **the mean accuracy across the three random seeds with one standard deviation as the variance bar**. Per-category accuracy is the unweighted mean over the three seeds. Cost and token figures are the per-seed mean (so they compare directly to a single-seed run).

**Claude Sonnet 4 caveat.** The Anthropic Messages API does not expose a `seed` parameter. Claude's three "seeds" are therefore three independent temperature-1.0 samples from the same input distribution, not seed-determined samples. The resulting variance estimate is still valid as a statistical measure of run-to-run variance; it just isn't replayable bit-for-bit the way the Vertex MaaS runs are.

### Replay

To regenerate `leaderboard.csv`, `per_category.csv`, and `per_case.csv` from the GCS results:

```bash
python scripts/compile_final_results.py \
    --config paper/final_results/sources.yaml \
    --out-dir paper/final_results
```

The three CSVs are committed to the repo. Diff-checking the freshly-regenerated CSVs against the committed copies is the reproducibility test:

```bash
# Should print nothing
diff <(git show HEAD:paper/final_results/leaderboard.csv) paper/final_results/leaderboard.csv
```

If the GCS results have not changed and the script has not changed, the CSVs are byte-identical (modulo float formatting).

### Downstream artifacts

Updating the paper after a re-run is a three-step flow:

```bash
python scripts/compile_final_results.py   # regenerate CSVs from GCS
python paper/generate_figures.py          # regenerate 8 figures
# then update the leaderboard table cells in the two .tex files
# (one row per model — values come straight from leaderboard.csv)
```

`paper/final_results/leaderboard.csv` is the single source of truth for every leaderboard number quoted in the paper, the README, the HF dataset card, and the figure data arrays.
