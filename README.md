# GeoNatureAgent Benchmark

A benchmark for evaluating LLM agents on environmental geospatial analysis through structured tool calling against a production API.

**93 tasks** | **18 categories** | **12 tools** | **8 models evaluated**

> **Paper**: *GeoNatureAgent Benchmark: Benchmarking LLM Agents for Environmental Geospatial Analysis*
> Gabriel Diaz-Ireland, Diego Prieto-Herráez, Javier Velázquez, Mario García Peces, Guillermo Perez (2026)

---

## What is GeoNatureAgent Benchmark?

Environmental scientists spend disproportionate effort on data wrangling rather than analysis. GeoNatureAgent Benchmark measures how well AI agents can automate these workflows by orchestrating geospatial tools against a real API serving three environmental indicators across Spain and Portugal.

Tasks span municipality-level analysis, multi-turn conversation, spatial reasoning, cross-indicator synthesis, error handling, ranking, comparison, multilingual understanding, habitat analysis, temporal change detection, and more.

**Key findings** (8 models evaluated):
- Best models (GLM-5 and Claude Sonnet 4) achieve 58.1% accuracy — environmental geospatial tool orchestration remains an open challenge
- Cost varies by two orders of magnitude: DeepSeek V3.2 achieves 52.7% at $0.008/case vs Claude Sonnet 4 at $0.087/case
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
| [`HOWTOUSE.md`](HOWTOUSE.md) | How to evaluate your own agent, add tasks, extend the benchmark |
| [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) | End-to-end reproduction guide (experiments, figures, paper) |
| [`geoagentbench/README.md`](geoagentbench/README.md) | CLI reference, output format, metrics |
| [`geoagentbench/cases/README.md`](geoagentbench/cases/README.md) | Task definitions, categories, JSON schema |
| [`hf_dataset/README.md`](hf_dataset/README.md) | HuggingFace dataset card |

---

## Repository Structure

```
GeoNatureAgent Benchmark/
├── README.md                    # This file
├── HOWTOUSE.md                  # Integration guide
├── REPRODUCIBILITY.md           # Reproduction guide
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
│   ├── results.jsonl            # 744 results (93 x 8 models)
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

## Leaderboard (v5, 93 tasks)

| # | Model | Accuracy | Cost/case | Access |
|---|-------|----------|-----------|--------|
| 1 | GLM-5 | 58.1% | $0.027 | Vertex AI MaaS |
| 1 | Claude Sonnet 4 | 58.1% | $0.087 | Anthropic API |
| 3 | DeepSeek V3.2 | 52.7% | $0.008 | Vertex AI MaaS |
| 4 | Qwen3-235B | 47.3% | $0.005 | Vertex AI MaaS |
| 5 | Gemini 2.5 Pro | 39.8% | $0.032 | Vertex AI native |
| 5 | GPT-OSS-120B | 39.8% | $0.051 | Vertex AI MaaS |
| 7 | Llama 4 Scout | 5.4% | $0.000 | Vertex AI MaaS |
| 8 | Llama 4 Maverick | 0.0% | --- | Vertex AI MaaS |

---

## Citation

If you use GeoNatureAgent Benchmark in your research, please cite:

```bibtex
@article{diazireland2026geoagentbench,
  title   = {GeoNatureAgent Benchmark: Benchmarking LLM Agents for Environmental Geospatial Analysis},
  author  = {Diaz-Ireland, Gabriel and Prieto-Herr{\'a}ez, Diego and Vel{\'a}zquez, Javier and Garc{\'i}a Peces, Mario and Perez, Guillermo},
  year    = {2026},
  url     = {https://github.com/darwin-geo/GeoNatureAgent}
}
```

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
