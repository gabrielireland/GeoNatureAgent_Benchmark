"""BigQuery logging for benchmark case results.

Streams one row per scored case to a partitioned BigQuery table.
All operations are non-fatal — failures log warnings but never block the run.
"""

import logging
import warnings
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from geoagentbench.scoring import ScoredResult

logger = logging.getLogger(__name__)


# ── Schema ──────────────────────────────────────────────────────────────────

_TABLE_ID = "case_results"

_SCHEMA = [
    ("run_id", "STRING"),
    ("experiment_id", "STRING"),
    ("case_id", "STRING"),
    ("model_id", "STRING"),
    ("prompt_strategy", "STRING"),
    ("prompt_version", "STRING"),
    ("passed", "BOOLEAN"),
    ("check_score", "FLOAT"),
    ("quality_check_score", "FLOAT"),
    ("cost_usd", "FLOAT"),
    ("duration_ms", "INTEGER"),
    ("rounds", "INTEGER"),
    ("input_tokens", "INTEGER"),
    ("output_tokens", "INTEGER"),
    ("tools_used", "STRING"),  # JSON array
    ("error", "STRING"),
    ("error_category", "STRING"),
    ("category", "STRING"),
    ("difficulty", "STRING"),
    ("keyword_coverage", "FLOAT"),
    ("tool_f1", "FLOAT"),
    ("git_commit", "STRING"),
    ("timestamp", "TIMESTAMP"),
]


def _get_bq_schema():
    """Build BigQuery SchemaField list from _SCHEMA definition."""
    from google.cloud.bigquery import SchemaField

    return [SchemaField(name, field_type) for name, field_type in _SCHEMA]


# ── Public API ──────────────────────────────────────────────────────────────


def ensure_dataset_and_table(
    dataset_id: str,
    project: Optional[str] = None,
) -> Optional[str]:
    """Auto-create dataset + case_results table with time partitioning.

    Returns the full table reference string (project.dataset.table) on success,
    or None on failure.
    """
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=project)
        dataset_ref = f"{client.project}.{dataset_id}"

        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset, exists_ok=True)

        table_ref = f"{dataset_ref}.{_TABLE_ID}"
        table = bigquery.Table(table_ref, schema=_get_bq_schema())
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="timestamp",
        )
        client.create_table(table, exists_ok=True)

        logger.info("BigQuery table ready: %s", table_ref)
        return table_ref
    except Exception as exc:
        warnings.warn(f"BigQuery setup failed (non-fatal): {exc}", stacklevel=2)
        return None


def log_row(
    table_ref: str,
    run_id: str,
    result: ScoredResult,
    experiment_id: str,
    model_id: str,
    prompt_strategy: str,
    prompt_version: str,
    git_commit: str,
) -> bool:
    """Insert one case-result row into BigQuery. Returns True on success."""
    try:
        import json

        from google.cloud import bigquery

        client = bigquery.Client()

        metadata = result.metadata or {}
        row = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "case_id": result.case_id,
            "model_id": model_id,
            "prompt_strategy": prompt_strategy,
            "prompt_version": prompt_version,
            "passed": result.passed,
            "check_score": result.check_score,
            "quality_check_score": result.quality_check_score,
            "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms,
            "rounds": result.rounds,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "tools_used": json.dumps(result.tools_used),
            "error": result.error,
            "error_category": result.error_category,
            "category": metadata.get("category", ""),
            "difficulty": metadata.get("difficulty", ""),
            "keyword_coverage": result.keyword_coverage,
            "tool_f1": result.tool_f1,
            "git_commit": git_commit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        errors = client.insert_rows_json(table_ref, [row])
        if errors:
            warnings.warn(f"BigQuery insert errors (non-fatal): {errors}", stacklevel=2)
            return False
        return True
    except Exception as exc:
        warnings.warn(f"BigQuery log_row failed (non-fatal): {exc}", stacklevel=2)
        return False
