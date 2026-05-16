#!/usr/bin/env python3
"""Prepare HuggingFace dataset from benchmark sources of truth.

Reads:
  - geoagentbench/cases/benchmark_v5.json  → hf_dataset/tasks.jsonl
  - /tmp/geoagentbench_v5_results/*.jsonl  → hf_dataset/results.jsonl

Usage:
    python scripts/prepare_hf_dataset.py
    python scripts/prepare_hf_dataset.py --results-dir /path/to/results
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASES_FILE = REPO / "geoagentbench" / "cases" / "benchmark_v5.json"
HF_DIR = REPO / "hf_dataset"

MODEL_MAP = {
    "exp_035_gemini25_pro_v5_seeds5":   "gemini-2.5-pro",
    "exp_036_deepseek_v32_v5_seeds5":   "deepseek-v3.2",
    "exp_038_gpt_oss_120b_v5_seeds5":   "gpt-oss-120b",
    "exp_039_glm5_v5_seeds5":           "glm-5",
    "exp_040_qwen3_235b_v5_seeds5":     "qwen3-235b",
    "exp_041_llama4_scout_v5_seeds5":   "llama-4-scout",
    "exp_042_claude_sonnet4_v5_seeds5": "claude-sonnet-4",
}

TASK_FIELDS = [
    "id",
    "category",
    "difficulty",
    "description",
    "question",
    "expected_tools",
    "expected_actions",
    "must_contain",
    "must_not_contain",
    "max_rounds",
    "max_cost_usd",
    "ground_truth_notes",
]

RESULT_FIELDS = [
    "case_id",
    "passed",
    "error_category",
    "rounds",
    "tools_used",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "duration_ms",
    "check_score",
    "tool_f1",
    "keyword_coverage",
]


def prepare_tasks() -> int:
    cases = json.loads(CASES_FILE.read_text())
    tasks_path = HF_DIR / "tasks.jsonl"
    with open(tasks_path, "w") as f:
        for case in cases:
            row = {k: case.get(k) for k in TASK_FIELDS}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(cases)


def prepare_results(results_dir: Path, valid_ids: set[str]) -> int:
    results_path = HF_DIR / "results.jsonl"
    total = 0
    with open(results_path, "w") as f:
        for jsonl_file in sorted(results_dir.glob("*.jsonl")):
            exp_id = jsonl_file.stem
            model_id = MODEL_MAP.get(exp_id, exp_id)
            for line in jsonl_file.read_text().strip().splitlines():
                record = json.loads(line)
                if record.get("case_id") not in valid_ids:
                    continue
                row = {"model_id": model_id, "experiment_id": exp_id}
                for k in RESULT_FIELDS:
                    row[k] = record.get(k)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                total += 1
    return total


def main():
    parser = argparse.ArgumentParser(description="Prepare HuggingFace dataset")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("/tmp/geoagentbench_v5_results"),
        help="Directory containing per-model results.jsonl files",
    )
    args = parser.parse_args()

    HF_DIR.mkdir(exist_ok=True)

    cases = json.loads(CASES_FILE.read_text())
    valid_ids = {c["id"] for c in cases}

    n_tasks = prepare_tasks()
    print(f"Wrote {n_tasks} tasks to hf_dataset/tasks.jsonl")

    if args.results_dir.exists():
        n_results = prepare_results(args.results_dir, valid_ids)
        print(f"Wrote {n_results} results to hf_dataset/results.jsonl")
    else:
        print(f"Results dir not found: {args.results_dir} — skipping results.jsonl")


if __name__ == "__main__":
    main()
