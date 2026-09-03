# GeoNatureAgent Benchmark

A framework and benchmark for choosing which LLM to run your geospatial-engineering agents on — evaluated through structured tool calling against a production API, with open data and everything needed to reproduce it.

**103 tasks** (93-task main suite + 10-task v6 expansion) | **18 categories** | **16 tools** | **9 models evaluated**

> **Paper**: *GeoNatureAgent Benchmark: Benchmarking LLM Agents for Environmental Geospatial Analysis*
> Gabriel Diaz-Ireland, Diego Prieto-Herráez, Mario García Peces, Javier Velázquez, Devika Jain (2026)

---

## What is GeoNatureAgent Benchmark?

Environmental scientists spend disproportionate effort on data wrangling rather than analysis. GeoNatureAgent Benchmark is a framework — and benchmark — for choosing which models best automate these workflows, by orchestrating geospatial tools against a real, open API serving three environmental indicators across Spain and Portugal.

Tasks span municipality-level analysis, multi-turn conversation, spatial reasoning, cross-indicator synthesis, error handling, ranking, comparison, multilingual understanding, habitat analysis, temporal change detection, and more.

**Key findings** (9 models evaluated):
- Best model (Claude Sonnet 4) achieves 60.8% ± 0.8% on the 93-task main suite (61.7% on the combined 103 tasks) — environmental geospatial tool orchestration remains an open challenge
- Cost varies by two orders of magnitude: Llama 4 Scout at $0.003/case and DeepSeek V3.2 (56.3%) at $0.011/case vs Claude Sonnet 4 at $0.127/case
- The cost-accuracy Pareto frontier is occupied mostly by open-weight models
- Comparison, temporal change, and interpretation are the universally hard categories

---

## Quick Start

```bash
# Install
pip install -e .

# Smoke test (6 dev cases)
python -m geoagentbench --cases dev

# Full benchmark (93 cases)
python -m geoagentbench --cases v5 --experiment benchmark/experiment.yaml --output-dir results/

# Run with a specific model
python -m geoagentbench --cases v5 --model vertex_ai/gemini-2.5-pro
```

See [`geoagentbench/README.md`](geoagentbench/README.md) for full CLI reference and output format.

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/HOWTOUSE.md`](docs/HOWTOUSE.md) | How to evaluate your own agent, add tasks, extend the benchmark |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | End-to-end reproduction guide (experiments, figures, paper) |
| [`docs/DATA_README.md`](docs/DATA_README.md) | Data archive specs (COGs, boundaries, sources) |
| [`geoagentbench/README.md`](geoagentbench/README.md) | CLI reference, output format, metrics |
| [`geoagentbench/cases/README.md`](geoagentbench/cases/README.md) | Task definitions, categories, JSON schema |
| [`hf_dataset/README.md`](hf_dataset/README.md) | HuggingFace dataset card |

---

## Repository Structure

```
GeoNatureAgent Benchmark/
├── README.md                    # This file
├── docs/                        # HOWTOUSE, REPRODUCIBILITY, DATA_README, PENDING
├── LICENSE                      # Apache 2.0
├── CITATION.cff                 # Citation metadata
├── pyproject.toml               # Python package config
├── geoagentbench/               # Benchmark framework
│   ├── runner.py                # Experiment runner
│   ├── scoring.py               # Evaluation checks (8 check types)
│   ├── llm_client.py            # Multi-backend LLM client (Anthropic + Vertex AI + OpenRouter)
│   ├── case_loader.py           # Task loader
│   ├── config.py                # Experiment YAML parser
│   ├── metrics.py               # Cost calculation, accuracy aggregation
│   └── cases/                   # Task definitions (JSON)
│       ├── benchmark_v5.json    # 93 tasks, 18 categories (paper)
│       └── benchmark_v6_expansion.json  # 10 comparison-heavy tasks (v6)
├── api/                         # Agent resources
│   ├── agent/prompts/v3.md      # System prompt (v3, used in all experiments)
│   └── data/                    # Pre-computed indicator data
│       ├── bigearthnet_portugal_stats.json
│       └── portugal_districts.json
├── benchmark/                   # Experiment configurations
│   ├── experiment.yaml          # Template
│   └── experiments/             # Per-model configs (9 v5 + 7 v6 experiments)
├── hf_dataset/                  # HuggingFace dataset
│   ├── tasks.jsonl              # 93 task definitions
│   ├── results.jsonl            # 1860 results (7 paper models; 9-model refresh pending)
│   └── README.md                # Dataset card
├── paper/                       # LaTeX manuscript + figures
│   ├── geonatureagent_benchmark.tex
│   ├── references.bib
│   └── figures/                 # 8 publication figures (PDF + PNG)
└── scripts/                     # Utilities
    ├── verify_package.py        # Package consistency checker (34 checks)
    ├── prepare_hf_dataset.py    # Generate HF dataset from sources
    ├── add_benchmark_case.py    # Add new benchmark tasks
    ├── visualize_benchmark.py   # Generate benchmark report charts
    └── compare_experiments.py   # Cross-experiment comparison
```

---

## Capability Leaderboard (v5, 93 tasks, mean ± std across seeds)

Capability and cost are reported as orthogonal axes — `max_cost_usd` is logged but not gated on binary pass/fail (see paper §3.3).

| # | Model | Capability | Cost/case | Access |
|---|-------|------------|-----------|--------|
| 1 | Claude Sonnet 4 | 60.8% ± 0.8† | $0.127 | Anthropic API |
| 2 | DeepSeek V3.2 | 56.3% ± 3.1 | $0.011 | Vertex AI MaaS |
| 3 | GLM-5 | 50.2% ± 2.2 | $0.038 | Vertex AI MaaS |
| 4 | Gemini 2.5 Pro | 48.0% ± 3.3 | $0.052 | Vertex AI native |
| 5 | GPT-4o | 41.6% ± 2.7 | $0.070 | OpenRouter |
| 6 | Qwen3-235B | 41.2% ± 4.3 | $0.010 | Vertex AI MaaS |
| 7 | GPT-OSS-120B | 34.1% ± 1.2 | $0.089 | Vertex AI MaaS |
| 8 | Llama 4 Scout | 26.9% ± 2.1 | $0.003 | Vertex AI MaaS |
| 9 | Gemma-3-27B | 15.8% ± 1.6 | $0.062 | OpenRouter |

† Claude Sonnet 4 is reported from two temperature-1.0 samples (the Anthropic Messages API does not implement deterministic seeding); the other eight models are evaluated under three seeds {42, 1337, 2024}.

**Cost–accuracy Pareto frontier:** Llama 4 Scout → Qwen3-235B → DeepSeek V3.2 → Claude Sonnet 4. Three of the four frontier models are open-weight.

**Combined 103-task leaderboard** (main suite + v6 expansion, capability scoring): see `paper/final_results/leaderboard_v5plus6.csv`, regenerated by `python3 -m scripts.aggregate_combined`. Ordering matches the 93-task table above (Qwen3-235B and GPT-4o swap within noise).

---

## Citation

If you use GeoNatureAgent Benchmark in your research, please cite:

```bibtex
@inproceedings{diazireland2026geonatureagent,
  title     = {GeoNatureAgent Benchmark: Benchmarking LLM Agents for Environmental Geospatial Analysis Across Frontier and Open-Weight Foundation Models},
  author    = {Diaz-Ireland, Gabriel and Prieto-Herr{\'a}ez, Diego and Garc{\'i}a Peces, Mario and Vel{\'a}zquez, Javier and Jain, Devika},
  booktitle = {The 34th ACM International Conference on Advances in Geographic Information Systems (SIGSPATIAL '26)},
  year      = {2026},
  publisher = {ACM},
  doi       = {10.1145/3841645.3844198}
}
```

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
