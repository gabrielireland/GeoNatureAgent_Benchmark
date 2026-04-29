"""Infrastructure preflight checks for Cloud Run experiments.

Verifies that the model API is reachable before the benchmark starts.
Can be run manually or added as the first step in entrypoint.sh.

Usage:
    python -m geoagentbench.preflight --experiment experiment.yaml --output-dir /tmp/output
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path


def check_anthropic_connectivity(model_id: str) -> tuple:
    """Make a minimal 1-token completion to verify the Anthropic API key.

    Returns:
        (reachable: bool, error: str)
    """
    try:
        from api.agent.secret_manager import get_anthropic_api_key
        import anthropic

        client = anthropic.Anthropic(api_key=get_anthropic_api_key())
        client.messages.create(
            model=model_id,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return True, ""
    except Exception as exc:
        return False, str(exc)


def check_vertex_connectivity(model_id: str, project_id: str, region: str) -> tuple:
    """Make a minimal 1-token completion to verify ADC + Vertex AI access.

    Uses the same routing as LiteLLMClient: Model Garden MaaS models
    (e.g. meta/llama) go through the OpenAI-compatible endpoint;
    native Gemini models go through the publisher endpoint.

    Returns:
        (reachable: bool, error: str)
    """
    try:
        from geoagentbench.llm_client import LiteLLMClient

        client = LiteLLMClient(
            model_id=model_id,
            vertex_project=project_id,
            vertex_region=region,
        )
        client.create_message(
            system="You are a test.",
            messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            tools=[],
            max_tokens=1,
        )
        return True, ""
    except Exception as exc:
        return False, str(exc)


def check_gcs_permissions(bucket: str, prefix: str) -> tuple:
    """Write and delete a test blob to verify GCS write access.

    Returns:
        (accessible: bool, error: str)
    """
    if not bucket:
        return True, ""  # GCS not configured — skip check
    try:
        from google.cloud import storage

        client = storage.Client()
        bucket_obj = client.bucket(bucket)
        test_blob_name = f"{prefix.strip('/')}/_preflight_test_{uuid.uuid4().hex[:8]}" if prefix else f"_preflight_test_{uuid.uuid4().hex[:8]}"
        blob = bucket_obj.blob(test_blob_name)
        blob.upload_from_string(b"preflight")
        blob.delete()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def check_bigquery_permissions(dataset_id: str) -> tuple:
    """Verify that the BigQuery dataset is accessible.

    Returns:
        (accessible: bool, error: str)
    """
    if not dataset_id:
        return True, ""  # BQ not configured — skip check
    try:
        from google.cloud import bigquery

        client = bigquery.Client()
        dataset_ref = f"{client.project}.{dataset_id}"
        client.get_dataset(dataset_ref)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def check_cases_loadable(config) -> tuple:
    """Verify that benchmark case files load and are non-empty.

    Returns:
        (loadable: bool, error: str)
    """
    try:
        from geoagentbench.case_loader import load_cases

        cases = load_cases(
            case_set=config.case_set,
            case_file=config.case_file,
            filter_ids=config.case_ids,
            filter_categories=config.categories,
        )
        if not cases:
            return False, f"No cases found for case_set='{config.case_set}'"
        return True, ""
    except Exception as exc:
        return False, str(exc)


def run_preflight(experiment_path: str, output_dir: str) -> dict:
    """Run preflight checks and write results to preflight.json."""
    from geoagentbench.config import load_experiment_config

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    config = load_experiment_config(experiment_path)
    model_id = config.model_id
    client_kwargs = config.client_kwargs
    vertex_project = client_kwargs.get("vertex_project", "")
    vertex_region = client_kwargs.get("vertex_region", "")

    print(f"Experiment: {experiment_path}")
    print(f"Model:      {model_id}")

    # Model connectivity (fatal)
    if model_id.startswith("vertex_ai/"):
        print(f"Checking Vertex AI connectivity (project={vertex_project}, region={vertex_region})...")
        model_reachable, model_error = check_vertex_connectivity(model_id, vertex_project, vertex_region)
    else:
        print("Checking Anthropic API connectivity...")
        model_reachable, model_error = check_anthropic_connectivity(model_id)

    print(f"Model reachable: {model_reachable}" + (f" — {model_error}" if model_error else ""))

    # Cases loadable (fatal)
    print("Checking cases loadable...")
    cases_ok, cases_error = check_cases_loadable(config)
    print(f"Cases loadable: {cases_ok}" + (f" — {cases_error}" if cases_error else ""))

    # GCS permissions (non-fatal warning)
    gcs_ok, gcs_error = True, ""
    if config.gcs_bucket:
        print(f"Checking GCS permissions (bucket={config.gcs_bucket})...")
        gcs_ok, gcs_error = check_gcs_permissions(config.gcs_bucket, config.output_prefix)
        if not gcs_ok:
            print(f"  WARNING: GCS check failed (non-fatal) — {gcs_error}")
        else:
            print("  GCS: OK")

    # BigQuery permissions (non-fatal warning)
    bq_ok, bq_error = True, ""
    if config.log_to_bigquery and config.bigquery_dataset:
        print(f"Checking BigQuery permissions (dataset={config.bigquery_dataset})...")
        bq_ok, bq_error = check_bigquery_permissions(config.bigquery_dataset)
        if not bq_ok:
            print(f"  WARNING: BigQuery check failed (non-fatal) — {bq_error}")
        else:
            print("  BigQuery: OK")

    # Fatal checks determine status
    all_fatal_ok = model_reachable and cases_ok

    results = {
        "experiment": experiment_path,
        "model_id": model_id,
        "vertex_project": vertex_project,
        "vertex_region": vertex_region,
        "model_reachable": model_reachable,
        "model_error": model_error,
        "cases_loadable": cases_ok,
        "cases_error": cases_error,
        "gcs_accessible": gcs_ok,
        "gcs_error": gcs_error,
        "bigquery_accessible": bq_ok,
        "bigquery_error": bq_error,
        "status": "READY" if all_fatal_ok else "NOT_READY",
    }

    results_path = output_path / "preflight.json"
    results_path.write_text(json.dumps(results, indent=2))
    print(f"Preflight results: {results_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="GeoNatureAgent Benchmark preflight checks")
    parser.add_argument("--experiment", required=True, help="Path to experiment YAML")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    args = parser.parse_args()

    results = run_preflight(args.experiment, args.output_dir)
    if results["status"] != "READY":
        print(f"PREFLIGHT FAILED: {results.get('model_error') or results.get('cases_error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
