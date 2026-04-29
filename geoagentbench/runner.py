"""Benchmark experiment runner.

Runs inside Docker on a GCP VM. All config comes from the experiment YAML;
credentials come from infrastructure (ADC, Secret Manager, DOCKER_ENV_ARGS).

Invoked by run_experiment.sh:
    python3 -m geoagentbench --experiment /experiment/experiment.yaml --output-dir /workspace_output
"""

import argparse
import dataclasses
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from geoagentbench.case_loader import load_cases
from geoagentbench.config import ExperimentConfig, load_experiment_config
from geoagentbench.llm_client import create_client
from geoagentbench.logging_structured import BenchmarkLogger
from geoagentbench.metrics import compute_cost
from geoagentbench.scoring import ScoredResult, score_result


def _validate_config(config: ExperimentConfig) -> None:
    """Validate config. Exits on failure."""
    errors = config.validate()
    if errors:
        print("CONFIG ERRORS:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


def _run_case_in_process(conn, case, model_id, client_kwargs):
    """Target function for the child process. Runs run_agent and sends result back via Pipe."""
    try:
        from geoagentbench.llm_client import create_client
        from agent.agent import run_agent
        from agent.session import session_store

        llm_client = create_client(model_id, **client_kwargs)

        session_id = None
        if case.get("session_history"):
            import time as _t
            session_id = f"bench-{case['id']}-{int(_t.time())}"
            session_store.save_messages(session_id, case["session_history"])

        result = run_agent(
            question=case["question"],
            aoi=case.get("aoi"),
            session_id=session_id,
            llm_client=llm_client,
            model_id=model_id,
        )
        conn.send(("ok", result))
    except Exception as exc:
        conn.send(("error", str(exc)))
    finally:
        conn.close()


def run_single_case(
    case: dict,
    config: ExperimentConfig,
    llm_client=None,
    case_timeout_sec: int = 300,
) -> Dict:
    """Run one eval case through the agent and return raw output + timing.

    Uses a subprocess (multiprocessing.Process) with a hard timeout.
    If the case hangs, the process is killed — no leaked threads or locks.
    Note: llm_client is NOT passed to the child process; the child creates
    its own client via the model_id (LiteLLM path).
    """
    import multiprocessing

    case_id = case["id"]
    question = case["question"]

    print(f"  Running: {question[:60]}...", flush=True)
    t0 = time.time()

    parent_conn, child_conn = multiprocessing.Pipe(duplex=False)
    proc = multiprocessing.Process(
        target=_run_case_in_process,
        args=(child_conn, case, config.model_id, config.client_kwargs),
    )
    proc.start()
    child_conn.close()

    # Wait for result with timeout
    if parent_conn.poll(timeout=case_timeout_sec):
        try:
            status, payload = parent_conn.recv()
        except EOFError:
            status, payload = "error", "Child process closed unexpectedly"
    else:
        status, payload = "timeout", None

    elapsed = int((time.time() - t0) * 1000)

    if status == "timeout" and proc.is_alive():
        print(f"  TIMEOUT: case {case_id} exceeded {case_timeout_sec}s — killing", flush=True)
        proc.kill()
        proc.join(timeout=5)
    elif proc.is_alive():
        proc.join(timeout=5)

    parent_conn.close()

    if status == "timeout" or status == "error":
        error_msg = payload if status == "error" else f"Case timed out after {case_timeout_sec}s"
        return {
            "case_id": case_id,
            "error": error_msg,
            "answer": None,
            "full_answer": "",
            "tools_used": [],
            "actions": [],
            "usage": {},
            "conversation_trace": [],
            "analysis_results": [],
            "_duration_ms": elapsed,
        }

    result = payload
    result["_duration_ms"] = elapsed
    return result


def _plot_benchmark_report(
    results: List[ScoredResult],
    config,
    output_dir: str,
) -> None:
    """Save benchmark_report.png to output_dir. Non-fatal on failure."""
    report_path = str(Path(output_dir) / "benchmark_report.png")
    try:
        from scripts.visualize_benchmark import plot_benchmark
        records = []
        for r in results:
            rec = dataclasses.asdict(r)
            rec["experiment_id"] = config.experiment_id
            rec["model_id"] = config.model_id
            records.append(rec)
        plot_benchmark(records, report_path)
        print(f"  Benchmark report: {report_path}")
    except Exception as e:
        print(f"  WARNING: visualization failed ({e}) — results still saved")


def _run_auto_comparison(
    config: ExperimentConfig,
    current_jsonl: Path,
    output_dir: str,
) -> None:
    """Generate comparison_report.png if config.compare_with is set. Non-fatal."""
    if not config.compare_with:
        return
    paths = [current_jsonl]
    tmp_dir = Path(output_dir)
    for ref in config.compare_with:
        if ref.startswith("gs://"):
            local = tmp_dir / f"_ref_{Path(ref).name}"
            try:
                subprocess.run(["gsutil", "cp", ref, str(local)],
                               check=True, capture_output=True)
                if local.exists():
                    paths.append(local)
            except Exception as e:
                print(f"  WARNING: could not download reference {ref}: {e}")
        else:
            p = Path(ref)
            if p.exists():
                paths.append(p)
            else:
                print(f"  WARNING: reference file not found: {ref}")
    if len(paths) < 2:
        print("  WARNING: auto-comparison skipped — fewer than 2 JSONL files available")
        return
    out = str(tmp_dir / "comparison_report.png")
    try:
        from scripts.compare_experiments import generate_comparison
        generate_comparison(paths, out)
        print(f"  Comparison report: {out}")
    except Exception as e:
        print(f"  WARNING: comparison chart failed ({e})")


def run_experiment(
    config: ExperimentConfig,
    output_dir: str,
    cases: Optional[list] = None,
) -> List[ScoredResult]:
    """Run a full benchmark experiment."""
    from geoagentbench.run_meta import RunMeta

    _validate_config(config)

    # Propagate prompt version to agent module (reads AGENT_PROMPT_VERSION at import time)
    os.environ["AGENT_PROMPT_VERSION"] = config.prompt_version

    if not config.is_enabled:
        reason = "stopped/retired" if config.enabled == "stop" else "disabled"
        print(f"\n  Experiment '{config.experiment_id}' is {reason} (enabled={config.enabled}). Skipping.")
        return []

    if cases is None:
        cases = load_cases(
            case_set=config.case_set,
            case_file=config.case_file,
            filter_ids=config.case_ids,
            filter_categories=config.categories,
        )

    if not cases:
        print("No cases to run.")
        return []

    client = create_client(config.model_id, **config.client_kwargs)
    logger = BenchmarkLogger(output_dir, config)
    meta = RunMeta(output_dir, logger.run_id, config, git_commit=logger.git_commit)
    meta.init()

    # Save frozen experiment YAML
    if config._source_yaml_path:
        logger.save_experiment_yaml(config._source_yaml_path)

    print(f"\n{'=' * 50}")
    print(f"  GeoAgentBench Runner")
    print(f"  Experiment:  {config.experiment_id}")
    print(f"  Run ID:      {logger.run_id}")
    print(f"  Model:       {config.model_id}")
    print(f"  Prompt:      {config.prompt_version} ({config.prompt_strategy})")
    print(f"  Architecture:{config.architecture}")
    print(f"  Cases:       {len(cases)}")
    print(f"  Output:      {output_dir}")
    print(f"{'=' * 50}\n")

    meta.start(n_cases=len(cases))

    results = []
    run_error = None
    try:
        for i, case in enumerate(cases, 1):
            print(f"\n  [{i}/{len(cases)}] {case['id']}")
            agent_output = run_single_case(case, config, llm_client=client)

            duration_ms = agent_output.get("_duration_ms", 0)
            usage = agent_output.get("usage", {})
            cost = compute_cost(
                config.model_id,
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )

            scored = score_result(
                case, agent_output, duration_ms, cost,
                question=case.get("question", ""),
            )

            # Extract chart GCS URIs populated by generate_chart tool calls
            chart_urls = agent_output.get("chart_urls", [])

            scored.metadata = {
                "category": case.get("category", ""),
                "difficulty": case.get("difficulty", ""),
                "ground_truth_notes": case.get("ground_truth_notes", ""),
                "chart_urls": chart_urls,
            }

            status = "PASS" if scored.passed else "FAIL"
            print(f"  Result: {status} | {duration_ms}ms | ${cost:.4f}")

            logger.log(scored)
            results.append(scored)

        summary_path = logger.write_summary()
        print_results(results)
        print(f"\n  Results saved: {summary_path}")

        _plot_benchmark_report(results, config, output_dir)
        _run_auto_comparison(config, logger.jsonl_path, output_dir)

        # Finalize run metadata BEFORE upload so _run_meta.json has final status
        total = len(results)
        passed = sum(1 for r in results if r.passed)

        # GCS upload (non-fatal)
        gcs_uri = None
        if config.gcs_bucket:
            from geoagentbench.gcs_upload import upload_directory

            # Pre-finalize so the uploaded _run_meta.json has status=completed
            meta.finalize(
                status="completed",
                summary={
                    "total": total,
                    "passed": passed,
                    "failed": total - passed,
                    "accuracy": round(passed / total, 4) if total else 0.0,
                    "cost_usd": round(sum(r.cost_usd for r in results), 4),
                },
            )

            gcs_uri = upload_directory(
                local_dir=output_dir,
                bucket_name=config.gcs_bucket,
                prefix=config.output_prefix,
                experiment_id=config.experiment_id,
            )

            # Update with GCS URI after upload
            meta.finalize(
                status="completed",
                summary={
                    "total": total,
                    "passed": passed,
                    "failed": total - passed,
                    "accuracy": round(passed / total, 4) if total else 0.0,
                    "cost_usd": round(sum(r.cost_usd for r in results), 4),
                },
                gcs_uri=gcs_uri,
            )
        else:
            meta.finalize(
                status="completed",
                summary={
                    "total": total,
                    "passed": passed,
                    "failed": total - passed,
                    "accuracy": round(passed / total, 4) if total else 0.0,
                    "cost_usd": round(sum(r.cost_usd for r in results), 4),
                },
            )

    except Exception as exc:
        run_error = str(exc)
        meta.finalize(status="failed", error=run_error)
        raise

    return results


def print_results(results: List[ScoredResult]) -> None:
    """Print a summary table of results."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    print("\n" + "=" * 72)
    print(f"  RESULTS -- {passed}/{total} passed, {failed} failed")
    print("=" * 72)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        marker = "+" if r.passed else "X"
        print(f"\n  [{marker}] {status}  {r.case_id}")
        if r.description:
            print(f"           {r.description}")
        print(f"           Duration: {r.duration_ms}ms | Rounds: {r.rounds} | Cost: ${r.cost_usd:.4f}")
        print(f"           Tokens: in={r.input_tokens} out={r.output_tokens}")

        if r.error:
            print(f"           ERROR: {r.error}")

        failed_checks = [c for c in r.checks if not c["passed"]]
        if failed_checks:
            for c in failed_checks:
                detail = ""
                if c.get("missing"):
                    detail = f" (missing: {c['missing']})"
                elif c.get("actual_rounds"):
                    detail = f" (actual: {c['actual_rounds']})"
                print(f"           FAILED: {c['check']}{detail}")

    print("\n" + "-" * 72)
    total_cost = sum(r.cost_usd for r in results)
    total_tokens = sum(r.input_tokens + r.output_tokens for r in results)
    total_ms = sum(r.duration_ms for r in results)
    print(f"  Total: {total_ms}ms | {total_tokens} tokens | ${total_cost:.4f}")
    print("-" * 72 + "\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GeoAgentBench -- Benchmark runner for environmental geospatial AI agents",
    )
    parser.add_argument("--experiment", help="Path to experiment YAML config")
    parser.add_argument("--cases", default="dev", help="Case set: dev, v1, v2, all (default: dev)")
    parser.add_argument("--case-file", help="Path to custom cases JSON file")
    parser.add_argument("--model", help="Override model ID (e.g. claude-sonnet-4-20250514)")
    parser.add_argument("--prompt", default=None, help="Prompt version: v1, v2 (default: v2)")
    parser.add_argument("--output-dir", default="./results", help="Output directory (default: ./results)")
    parser.add_argument("--filter-ids", nargs="+", help="Run only these case IDs")
    parser.add_argument("--filter-categories", nargs="+", help="Run only these categories")
    args = parser.parse_args()

    # Build config from experiment YAML or CLI args
    if args.experiment:
        config = load_experiment_config(args.experiment)
    else:
        config = ExperimentConfig(
            experiment_id=f"cli_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            model_id=args.model or os.getenv("AGENT_MODEL_ID", "claude-sonnet-4-20250514"),
            prompt_version=args.prompt or os.getenv("AGENT_PROMPT_VERSION", "v2"),
            case_set=args.cases,
            case_file=args.case_file,
        )

    # CLI overrides
    if args.model:
        config.model_id = args.model
    if args.prompt:
        config.prompt_version = args.prompt
    if args.case_file:
        config.case_file = args.case_file
    elif args.cases != "dev" or not args.experiment:
        config.case_set = args.cases

    cases = load_cases(
        case_set=config.case_set,
        case_file=config.case_file,
        filter_ids=args.filter_ids or config.case_ids,
        filter_categories=args.filter_categories or config.categories,
    )

    if not cases:
        print(f"No matching cases found for set='{config.case_set}'.")
        from geoagentbench.case_loader import CASE_SETS
        print(f"Available case sets: {', '.join(CASE_SETS.keys())}, all")
        sys.exit(1)

    results = run_experiment(config, args.output_dir, cases=cases)

    if any(not r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
