"""Unified run metadata for benchmark experiments.

Replaces the separate RunContract + manifest with a single ``_run_meta.json``
file that tracks lifecycle, frozen config, environment, and summary.
"""

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from geoagentbench.config import ExperimentConfig


class RunMeta:
    """Tracks the full lifecycle and metadata of a single benchmark run."""

    def __init__(
        self,
        output_dir: str,
        run_id: str,
        config: ExperimentConfig,
        git_commit: str = "unknown",
    ):
        self.output_dir = Path(output_dir)
        self.run_id = run_id
        self.config = config
        self._path = self.output_dir / "_run_meta.json"
        self._data = {
            "run_id": run_id,
            "experiment_id": config.experiment_id,
            "model_id": config.model_id,
            "batch_id": os.environ.get("BUILD_ID", ""),
            "git_commit": git_commit,
            "status": "unknown",
            "timestamps": {},
            "config": {
                "model_id": config.model_id,
                "max_tokens": config.max_tokens,
                "architecture": config.architecture,
                "prompt_strategy": config.prompt_strategy,
                "prompt_version": config.prompt_version,
                "max_turns": config.max_turns,
                "case_set": config.case_set,
                "categories": config.categories,
                "case_ids": config.case_ids,
                "based_on": config.based_on,
                "vertex_project": config.vertex_project,
                "vertex_region": config.vertex_region,
                "sampling": {
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k,
                    "seed": config.seed,
                },
            },
            "environment": {
                "python_version": sys.version,
                "platform": platform.platform(),
                "packages": self._get_key_package_versions(),
            },
            "summary": {},
        }

    @staticmethod
    def _get_key_package_versions() -> dict:
        packages = {}
        for pkg in ("anthropic", "litellm", "google-cloud-bigquery", "google-cloud-storage", "pandas", "matplotlib"):
            try:
                from importlib.metadata import version
                packages[pkg] = version(pkg)
            except Exception:
                packages[pkg] = "not installed"
        return packages

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _write(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    def init(self) -> None:
        """Mark the run as initialised."""
        self._data["status"] = "init"
        self._data["timestamps"]["init"] = self._now()
        self._write()

    def start(self, n_cases: int) -> None:
        """Mark the run as started with *n_cases* to execute."""
        self._data["status"] = "running"
        self._data["timestamps"]["start"] = self._now()
        self._data["n_cases"] = n_cases
        self._write()

    def finalize(
        self,
        status: str = "completed",
        summary: Optional[dict] = None,
        gcs_uri: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Path:
        """Mark the run as finalised and write the meta file.

        Returns:
            Path to the _run_meta.json file.
        """
        self._data["status"] = status
        self._data["timestamps"]["finalize"] = self._now()
        if summary:
            self._data["summary"] = summary
        if gcs_uri:
            self._data["gcs_uri"] = gcs_uri
        if error:
            self._data["error"] = error
        self._write()
        return self._path

    @property
    def data(self) -> dict:
        """Return the current metadata dict."""
        return self._data
