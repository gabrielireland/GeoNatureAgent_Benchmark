# GeoNatureAgent Benchmark

A benchmark for evaluating LLM agents on environmental geospatial analysis through structured tool calling against a production API.

**93 tasks** | **18 categories** | **16 tools** | **7 models evaluated**

> **Paper**: *GeoNatureAgent Benchmark: Benchmarking LLM Agents for Environmental Geospatial Analysis*
> Gabriel Diaz-Ireland, Diego Prieto-Herráez, Mario García Peces, Javier Velázquez, Devika Jain (2026)

---

## What is GeoNatureAgent Benchmark?

Environmental scientists spend disproportionate effort on data wrangling rather than analysis. GeoNatureAgent Benchmark measures how well AI agents can automate these workflows by orchestrating geospatial tools against a real API serving three environmental indicators across Spain and Portugal.

Tasks span municipality-level analysis, multi-turn conversation, spatial reasoning, cross-indicator synthesis, error handling, ranking, comparison, multilingual understanding, habitat analysis, temporal change detection, and more.

**Key findings** (7 models evaluated):
- Best model (Claude Sonnet 4) achieves 60.8% ± 0.8% accuracy — environmental geospatial tool orchestration remains an open challenge
- Cost varies by two orders of magnitude: Llama 4 Scout at $0.003/case and DeepSeek V3.2 (56.3%) at $0.011/case vs Claude Sonnet 4 at $0.127/case
- Comparison and error recovery are universally hard categories

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
│   ├── llm_client.py            # Multi-backend LLM client (Anthropic + Vertex AI)
│   ├── case_loader.py           # Task loader
│   ├── config.py                # Experiment YAML parser
│   ├── metrics.py               # Cost calculation, accuracy aggregation
│   └── cases/                   # Task definitions (JSON)
│       └── benchmark_v5.json    # 93 tasks, 18 categories (paper)
├── api/                         # Agent resources
│   ├── agent/prompts/v3.md      # System prompt (v3, used in all experiments)
│   └── data/                    # Pre-computed indicator data
│       ├── bigearthnet_portugal_stats.json
│       └── portugal_districts.json
├── benchmark/                   # Experiment configurations
│   ├── experiment.yaml          # Template
│   └── experiments/             # Per-model configs (8 v5 experiments)
├── hf_dataset/                  # HuggingFace dataset
│   ├── tasks.jsonl              # 93 task definitions
│   ├── results.jsonl            # 1860 results (93 tasks × seeds × 7 models)
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
| 5 | Qwen3-235B | 41.2% ± 4.3 | $0.010 | Vertex AI MaaS |
| 6 | GPT-OSS-120B | 34.1% ± 1.2 | $0.089 | Vertex AI MaaS |
| 7 | Llama 4 Scout | 26.9% ± 2.1 | $0.003 | Vertex AI MaaS |

† Claude Sonnet 4 is reported from two temperature-1.0 samples (the Anthropic Messages API does not implement deterministic seeding); the other six models are evaluated under three seeds {42, 1337, 2024}.

**Cost–accuracy Pareto frontier:** Llama 4 Scout → Qwen3-235B → DeepSeek V3.2 → Claude Sonnet 4. Three of the four frontier models are open-weight.

---

## Citation

If you use GeoNatureAgent Benchmark in your research, please cite:

```bibtex
@article{diazireland2026geoagentbench,
  title   = {GeoNatureAgent Benchmark: Benchmarking LLM Agents for Environmental Geospatial Analysis},
  author  = {Diaz-Ireland, Gabriel and Prieto-Herr{\'a}ez, Diego and Garc{\'i}a Peces, Mario and Vel{\'a}zquez, Javier and Jain, Devika},
  year    = {2026},
  url     = {https://github.com/gabrielireland/GeoNatureAgent_Benchmark}
}
```

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
