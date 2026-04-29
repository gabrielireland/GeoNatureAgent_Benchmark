"""Structured JSONL logging for benchmark runs.

Writes per-case results and a run summary to the output directory.
Optionally streams rows to BigQuery.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from geoagentbench.config import ExperimentConfig
from geoagentbench.scoring import ScoredResult


class BenchmarkLogger:
    """Structured logger for benchmark experiment runs."""

    def __init__(self, output_dir: str, config: ExperimentConfig):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.results: List[ScoredResult] = []

        self._timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._git_commit = self._get_git_commit()
        self._run_id = f"{config.experiment_id}_{self._timestamp}_{uuid.uuid4().hex[:8]}"
        self._jsonl_path = self.output_dir / "results.jsonl"
        self._jsonl_file = open(self._jsonl_path, "w")

        # BigQuery streaming (non-fatal)
        self._bq_table_ref: Optional[str] = None
        if config.log_to_bigquery and config.bigquery_dataset:
            self._init_bigquery(config.bigquery_dataset)

    @property
    def run_id(self) -> str:
        """Unique identifier for this benchmark run."""
        return self._run_id

    @property
    def git_commit(self) -> str:
        """Git commit hash for this run."""
        return self._git_commit

    @property
    def jsonl_path(self) -> Path:
        """Path to the JSONL results file for this run."""
        return self._jsonl_path

    @staticmethod
    def _get_git_commit() -> str:
        """Resolve git commit from env vars first (Docker has no .git/), then fallback to git."""
        for env_var in ("SHORT_SHA", "GIT_COMMIT", "COMMIT_SHA"):
            val = os.environ.get(env_var, "").strip()
            if val:
                return val[:12]
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except Exception:
            return "unknown"

    def _init_bigquery(self, dataset_id: str) -> None:
        """Set up BigQuery table. Non-fatal on failure."""
        try:
            from geoagentbench.bq_logger import ensure_dataset_and_table

            self._bq_table_ref = ensure_dataset_and_table(dataset_id)
            if self._bq_table_ref:
                print(f"  BigQuery logging enabled: {self._bq_table_ref}")
        except Exception as exc:
            print(f"  WARNING: BigQuery init failed (non-fatal): {exc}")

    @staticmethod
    def _get_key_package_versions() -> dict:
        """Return versions of key benchmark packages."""
        packages = {}
        for pkg in ("anthropic", "litellm", "google-cloud-bigquery", "google-cloud-storage", "pandas", "matplotlib"):
            try:
                from importlib.metadata import version

                packages[pkg] = version(pkg)
            except Exception:
                packages[pkg] = "not installed"
        return packages

    def save_experiment_yaml(self, yaml_path: str) -> None:
        """Copy the raw experiment YAML file to output_dir/experiment.yaml."""
        src = Path(yaml_path)
        if src.exists():
            dst = self.output_dir / "experiment.yaml"
            shutil.copy2(str(src), str(dst))

    def log(self, result: ScoredResult) -> None:
        """Log a single case result to JSONL, accumulate for summary, and stream to BQ."""
        self.results.append(result)

        record = asdict(result)
        record["experiment_id"] = self.config.experiment_id
        record["model_id"] = self.config.model_id
        record["prompt_strategy"] = self.config.prompt_strategy
        record["prompt_version"] = self.config.prompt_version
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        record["git_commit"] = self._git_commit
        record["run_id"] = self._run_id
        # Surface chart_urls at the top level for easy discovery
        record["chart_urls"] = (result.metadata or {}).get("chart_urls", [])

        self._jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._jsonl_file.flush()

        # Stream to BigQuery (non-fatal)
        if self._bq_table_ref:
            try:
                from geoagentbench.bq_logger import log_row

                log_row(
                    table_ref=self._bq_table_ref,
                    run_id=self._run_id,
                    result=result,
                    experiment_id=self.config.experiment_id,
                    model_id=self.config.model_id,
                    prompt_strategy=self.config.prompt_strategy,
                    prompt_version=self.config.prompt_version,
                    git_commit=self._git_commit,
                )
            except Exception as exc:
                print(f"  WARNING: BQ streaming failed for {result.case_id} (non-fatal): {exc}")

    def write_summary(self) -> Path:
        """Write final summary JSON and close the JSONL file."""
        from geoagentbench.metrics import (
            accuracy_by_category,
            accuracy_by_difficulty,
            build_error_taxonomy,
            check_type_accuracy,
            cost_accuracy_summary,
        )

        self._jsonl_file.close()

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        agg = cost_accuracy_summary(self.results)

        # Compute avg action F1, tool precision, tool recall
        action_f1s = [r.action_f1 for r in self.results if r.action_f1 is not None]
        tool_precisions = [r.tool_precision for r in self.results if r.tool_precision is not None]
        tool_recalls = [r.tool_recall for r in self.results if r.tool_recall is not None]

        summary = {
            "run_id": self._run_id,
            "timestamp": self._timestamp,
            "git_commit": self._git_commit,
            "experiment_id": self.config.experiment_id,
            "based_on": self.config.based_on,
            "model_id": self.config.model_id,
            "prompt_strategy": self.config.prompt_strategy,
            "prompt_version": self.config.prompt_version,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "accuracy": round(passed / total, 4) if total else 0.0,
                "difficulty_weighted_accuracy": agg.get("difficulty_weighted_accuracy"),
                # Metric F: partial credit
                "avg_check_score": agg.get("avg_check_score"),
                "avg_quality_check_score": agg.get("avg_quality_check_score"),
            },
            "totals": {
                "input_tokens": sum(r.input_tokens for r in self.results),
                "output_tokens": sum(r.output_tokens for r in self.results),
                "cost_usd": round(sum(r.cost_usd for r in self.results), 4),
                "duration_ms": sum(r.duration_ms for r in self.results),
            },
            "efficiency": {
                "avg_rounds_utilization": agg.get("avg_rounds_utilization"),
                "avg_cost_utilization": agg.get("avg_cost_utilization"),
                "cases_near_limit_count": agg.get("cases_near_limit_count"),
                # Metric G/H/I averages
                "avg_keyword_coverage": agg.get("avg_keyword_coverage"),
                "avg_tool_f1": agg.get("avg_tool_f1"),
                "avg_tool_precision": round(sum(tool_precisions) / len(tool_precisions), 4) if tool_precisions else None,
                "avg_tool_recall": round(sum(tool_recalls) / len(tool_recalls), 4) if tool_recalls else None,
                "avg_action_f1": round(sum(action_f1s) / len(action_f1s), 4) if action_f1s else None,
                "avg_ms_per_round": agg.get("avg_ms_per_round"),
            },
            "accuracy_by_category": accuracy_by_category(self.results),
            "accuracy_by_difficulty": accuracy_by_difficulty(self.results),
            "check_type_accuracy": check_type_accuracy(self.results),
            "error_taxonomy": build_error_taxonomy(self.results),
            "results": [asdict(r) for r in self.results],
        }

        summary_path = self.output_dir / f"{self._timestamp}_{self.config.experiment_id}_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        return summary_path
