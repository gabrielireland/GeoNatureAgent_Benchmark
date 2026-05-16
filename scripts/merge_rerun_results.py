#!/usr/bin/env python3
"""[DEPRECATED] Merge re-run results into existing per-model results files.

DEPRECATION NOTE
================
This script implements the legacy `_v5 + _v5_rerun` merge workflow used during
the BigEarthNet integration phase. The paper now uses the `_v5_seeds5` runs as
the single source of truth (see `paper/final_results/sources.yaml`), so no
rerun merging is required. The YAMLs this script was designed to merge have
been archived under `benchmark/experiments/archive/`.

The script is retained for reference and historical reproducibility. New work
should use `scripts/compile_final_results.py` against the seeds5 runs instead.

Original usage (now obsolete):
    # Step 1: Download re-run results from GCS
    python scripts/merge_rerun_results.py --download \
        --gcs-run gs://geonature-agent-results/GeoNatureAgent/experiments/run_YYYYMMDD_HHMMSS

    # Step 2: Merge (dry run first)
    python scripts/merge_rerun_results.py --dry-run

    # Step 3: Merge for real
    python scripts/merge_rerun_results.py

    # Step 4: Propagate changes
    python scripts/merge_rerun_results.py --propagate
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The 20 BigEarthNet/habitat case IDs that were rewritten for the bigearthnet_lulc indicator.
# These cases were originally CLC-dependent and are now Portuguese BigEarthNet LULC cases.
# They need re-running because the agent prompt and case definitions changed.
RERUN_CASE_IDS = {
    "V5_31_habitat_province_single",
    "V5_32_habitat_forest_types",
    "V5_33_habitat_recall_grassland",
    "V5_34_habitat_chart",
    "V5_36_temporal_compare_shrubland",
    "V5_37_temporal_change_visual",
    "V5_38_cross_indicator_habitat_co2",
    "V5_56_habitat_andalucia_forest",
    "V5_57_temporal_multi_year",
    "V5_60_legend_habitat_classes",
    "V5_62_list_layers_habitat_years",
    "V5_67_multi_layer_three_indicators",
    "V5_68_multi_layer_nbs_profile",
    "V5_69_multi_layer_explicit_simultaneous",
    "V5_74_deep_dive_temporal_profile",
    "V5_82_layer_bounds_ceuta_melilla",
    "V5_86_multi_layer_with_chart_huelva",
    "V5_87_multi_layer_comparison_two_provinces",
    "V5_91_deep_dive_temporal_municipality",
    "V5_93_deep_dive_national_policy_brief",
}

# Maps rerun experiment_id to original experiment_id
RERUN_TO_ORIGINAL = {
    "exp_035_gemini25_pro_v5_rerun": "exp_035_gemini25_pro_v5",
    "exp_036_deepseek_v32_v5_rerun": "exp_036_deepseek_v32_v5",
    "exp_038_gpt_oss_120b_v5_rerun": "exp_038_gpt_oss_120b_v5",
    "exp_039_glm5_v5_rerun": "exp_039_glm5_v5",
    "exp_040_qwen3_235b_v5_rerun": "exp_040_qwen3_235b_v5",
    "exp_041_llama4_scout_v5_rerun": "exp_041_llama4_scout_v5",
    "exp_042_claude_sonnet4_v5_rerun": "exp_042_claude_sonnet4_v5",
}

DEFAULT_EXISTING = Path("/tmp/geoagentbench_v5_results")
DEFAULT_RERUN = Path("/tmp/geoagentbench_v5_rerun")


def load_jsonl(path: Path) -> list[dict]:
    lines = []
    for line in path.read_text().strip().splitlines():
        if line.strip():
            lines.append(json.loads(line))
    return lines


def download_rerun(gcs_run: str) -> None:
    """Download re-run results from GCS and rename to match original experiment IDs."""
    DEFAULT_RERUN.mkdir(parents=True, exist_ok=True)
    for rerun_id, original_id in sorted(RERUN_TO_ORIGINAL.items()):
        gcs_path = f"{gcs_run}/{rerun_id}/results.jsonl"
        local_path = DEFAULT_RERUN / f"{original_id}.jsonl"
        print(f"  {rerun_id} → {local_path.name}")
        result = subprocess.run(
            ["gcloud", "storage", "cp", gcs_path, str(local_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"    WARN: download failed — {result.stderr.strip()}")
        else:
            print(f"    OK ({local_path.stat().st_size} bytes)")


def merge_one(existing_path: Path, rerun_path: Path, dry_run: bool) -> dict:
    """Merge re-run results into an existing results file."""
    existing = load_jsonl(existing_path)
    rerun = load_jsonl(rerun_path)

    rerun_map = {r["case_id"]: r for r in rerun if r.get("case_id") in RERUN_CASE_IDS}

    replaced = 0
    old_passed = 0
    new_passed = 0
    merged = []

    for record in existing:
        cid = record.get("case_id")
        if cid in rerun_map:
            old_passed += int(record.get("passed", False))
            new_passed += int(rerun_map[cid].get("passed", False))
            merged.append(rerun_map[cid])
            replaced += 1
        else:
            merged.append(record)

    if not dry_run:
        with open(existing_path, "w") as f:
            for record in merged:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    total_passed = sum(1 for r in merged if r.get("passed"))
    accuracy = round(total_passed / len(merged) * 100, 1) if merged else 0.0

    return {
        "file": existing_path.name,
        "total": len(merged),
        "replaced": replaced,
        "old_passed": old_passed,
        "new_passed": new_passed,
        "total_passed": total_passed,
        "accuracy": accuracy,
    }


def merge_all(existing_dir: Path, rerun_dir: Path, dry_run: bool) -> list[dict]:
    """Merge all re-run results."""
    summaries = []
    for existing_file in sorted(existing_dir.glob("*.jsonl")):
        rerun_file = rerun_dir / existing_file.name
        if not rerun_file.exists():
            print(f"  SKIP {existing_file.name} — no matching re-run file")
            continue
        summary = merge_one(existing_file, rerun_file, dry_run=dry_run)
        summaries.append(summary)

    print(f"\n{'Experiment':<35} {'Replaced':>8} {'Old→New Pass':>15} {'Accuracy':>10}")
    print("-" * 72)
    for s in summaries:
        exp = s["file"].replace(".jsonl", "")
        print(
            f"{exp:<35} {s['replaced']:>8} "
            f"{s['old_passed']:>5}→{s['new_passed']:<5} "
            f"{s['accuracy']:>9.1f}%"
        )

    print("\nEXPECTED_ACCURACY for verify_package.py:")
    print("EXPECTED_ACCURACY = {")
    for s in summaries:
        exp = s["file"].replace(".jsonl", "")
        print(f'    "{exp}": {s["accuracy"]},')
    print("}")

    return summaries


def propagate(summaries: list[dict]) -> None:
    """Update all derived artifacts with new accuracy numbers."""
    if not summaries:
        # Recompute from existing results
        existing_dir = DEFAULT_EXISTING
        cases_file = REPO / "geoagentbench" / "cases" / "benchmark_v5.json"
        valid_ids = {c["id"] for c in json.loads(cases_file.read_text())}
        summaries = []
        for f in sorted(existing_dir.glob("*.jsonl")):
            records = [r for r in load_jsonl(f) if r.get("case_id") in valid_ids]
            passed = sum(1 for r in records if r.get("passed"))
            acc = round(passed / len(records) * 100, 1) if records else 0.0
            summaries.append({"file": f.name, "accuracy": acc, "total_passed": passed})

    acc_map = {s["file"].replace(".jsonl", ""): s["accuracy"] for s in summaries}

    # 1. Update verify_package.py
    print("Updating verify_package.py EXPECTED_ACCURACY...")
    vp = REPO / "scripts" / "verify_package.py"
    text = vp.read_text()
    new_block = "EXPECTED_ACCURACY = {\n"
    for exp_id in sorted(acc_map):
        new_block += f'    "{exp_id}": {acc_map[exp_id]},\n'
    new_block += "}"
    text = re.sub(
        r"EXPECTED_ACCURACY = \{[^}]+\}",
        new_block,
        text,
    )
    vp.write_text(text)

    # 2. Regenerate HF dataset
    print("Regenerating HF dataset...")
    subprocess.run([sys.executable, str(REPO / "scripts" / "prepare_hf_dataset.py")], check=True)

    # 3. Regenerate figures
    print("Regenerating figures...")
    subprocess.run(
        [sys.executable, str(REPO / "agentic_documentation" / "paper" / "generate_figures.py")],
        check=True,
    )

    # 4. Update leaderboard in READMEs
    print("Updating leaderboard numbers in READMEs...")
    sorted_models = sorted(acc_map.items(), key=lambda x: -x[1])

    model_names = {
        "exp_035_gemini25_pro_v5": "Gemini 2.5 Pro",
        "exp_036_deepseek_v32_v5": "DeepSeek V3.2",
        "exp_038_gpt_oss_120b_v5": "GPT-OSS-120B",
        "exp_039_glm5_v5": "GLM-5",
        "exp_040_qwen3_235b_v5": "Qwen3-235B",
        "exp_041_llama4_scout_v5": "Llama 4 Scout",
        "exp_042_claude_sonnet4_v5": "Claude Sonnet 4",
    }

    best_model = model_names.get(sorted_models[0][0], sorted_models[0][0])
    best_acc = sorted_models[0][1]

    # Find DeepSeek accuracy for the cost comparison line
    ds_acc = acc_map.get("exp_036_deepseek_v32_v5", 0.0)

    readme_files = [
        REPO / "README.md",
        REPO / "final_package" / "README.md",
    ]
    for readme in readme_files:
        if not readme.exists():
            continue
        txt = readme.read_text()
        # Update "Best model ... achieves XX.X% accuracy"
        txt = re.sub(
            r"Best model \([^)]+\) achieves [\d.]+% accuracy",
            f"Best model ({best_model}) achieves {best_acc}% accuracy",
            txt,
        )
        # Update "DeepSeek V3.2 achieves XX.X%"
        txt = re.sub(
            r"DeepSeek V3\.2 achieves [\d.]+%",
            f"DeepSeek V3.2 achieves {ds_acc}%",
            txt,
        )
        readme.write_text(txt)
        print(f"  Updated {readme.relative_to(REPO)}")

    # 5. Sync key files to final_package
    print("Syncing to final_package...")
    sync_pairs = [
        ("scripts/verify_package.py", "scripts/verify_package.py"),
        ("hf_dataset/tasks.jsonl", "hf_dataset/tasks.jsonl"),
        ("hf_dataset/results.jsonl", "hf_dataset/results.jsonl"),
    ]
    fp = REPO / "final_package"
    for src, dst in sync_pairs:
        src_path = REPO / src
        dst_path = fp / dst
        if src_path.exists():
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            dst_path.write_text(src_path.read_text())

    # Sync figures
    fig_src = REPO / "agentic_documentation" / "paper" / "figures"
    fig_dst = fp / "paper" / "figures"
    if fig_src.exists() and fig_dst.exists():
        for fig in fig_src.glob("fig*.*"):
            (fig_dst / fig.name).write_bytes(fig.read_bytes())

    # 6. Run verification
    print("\nRunning verify_package.py...")
    subprocess.run([sys.executable, str(REPO / "scripts" / "verify_package.py")], check=True)
    print("\nDone! Review the changes and commit.")


def main():
    parser = argparse.ArgumentParser(description="Merge re-run results and propagate changes")
    parser.add_argument(
        "--download", action="store_true",
        help="Download re-run results from GCS",
    )
    parser.add_argument(
        "--gcs-run", type=str,
        help="GCS run path (e.g. gs://bucket/GeoNatureAgent/experiments/run_YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--existing-dir", type=Path, default=DEFAULT_EXISTING,
        help="Directory with existing per-model results.jsonl files",
    )
    parser.add_argument(
        "--rerun-dir", type=Path, default=DEFAULT_RERUN,
        help="Directory with re-run per-model results.jsonl files",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing files",
    )
    parser.add_argument(
        "--propagate", action="store_true",
        help="After merging, update all derived artifacts (verify, HF, figures, READMEs)",
    )
    args = parser.parse_args()

    if args.download:
        if not args.gcs_run:
            print("ERROR: --gcs-run is required with --download")
            return 1
        print(f"Downloading re-run results from {args.gcs_run}...")
        download_rerun(args.gcs_run)
        print("\nDownload complete. Now run without --download to merge.")
        return 0

    if args.propagate:
        propagate([])
        return 0

    if not args.existing_dir.exists():
        print(f"ERROR: existing dir not found: {args.existing_dir}")
        return 1
    if not args.rerun_dir.exists():
        print(f"ERROR: rerun dir not found: {args.rerun_dir}")
        return 1

    print(f"Existing results: {args.existing_dir}")
    print(f"Re-run results:   {args.rerun_dir}")
    print(f"Cases to merge:   {len(RERUN_CASE_IDS)}")
    if args.dry_run:
        print("MODE: dry run (no files will be modified)\n")
    else:
        print("MODE: live (files will be modified)\n")

    summaries = merge_all(args.existing_dir, args.rerun_dir, dry_run=args.dry_run)

    if not args.dry_run:
        print("\nNext: python scripts/merge_rerun_results.py --propagate")


if __name__ == "__main__":
    main()
