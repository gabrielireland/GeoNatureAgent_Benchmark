#!/usr/bin/env python3
"""Add or validate benchmark cases for GeoNatureAgent Benchmark.

Interactive workflow to define a new case, validate it against the schema,
check ID uniqueness across all case files, and append it to a case set.

Usage:
    # Interactive mode — prompts for each field
    python scripts/add_benchmark_case.py --target v3

    # Validate an existing case file (no modifications)
    python scripts/add_benchmark_case.py --validate geoagentbench/cases/benchmark_v3.json

    # Validate all case files
    python scripts/add_benchmark_case.py --validate-all

    # Import a case from a JSON file and append to a target set
    python scripts/add_benchmark_case.py --import case.json --target v3
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from geoagentbench.case_loader import CASE_SETS, _CASES_DIR

# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"id", "question", "expected_tools"}

OPTIONAL_FIELDS = {
    "description": str,
    "category": str,
    "difficulty": str,
    "expected_actions": list,
    "must_contain": list,
    "must_not_contain": list,
    "ground_truth": list,
    "ground_truth_notes": str,
    "max_rounds": int,
    "max_cost_usd": float,
    "max_latency_ms": int,
    "session_history": list,
    "aoi": dict,
}

VALID_CATEGORIES = {
    "single_analysis", "comparison", "ranking", "interpretation", "memory",
    "language_understanding", "tool_selection", "error_handling",
    "spatial_reasoning", "cross_indicator", "municipality", "deep_dive",
    "poc",
    # v4 categories
    "habitat_analysis", "temporal_change",
    # v5 new categories
    "multi_municipality_ranking", "province_aggregation",
    "error_recovery", "threshold", "language",
    # erosion_v2 categories
    "erosion_analysis",
}

VALID_DIFFICULTIES = {"easy", "medium", "hard"}

VALID_TOOLS = {
    "list_layers", "get_legend", "analyze_area", "get_layer_bounds",
    "lookup_province", "lookup_municipality", "compare_areas", "find_top_n",
    "generate_chart", "analyze_multi_layer", "toggle_layer",
    # erosion_v2 tools
    "query_erosion_stats",
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_case(case: dict) -> list[str]:
    """Validate a single case dict. Returns list of error strings (empty = valid)."""
    errors = []

    for field in REQUIRED_FIELDS:
        if field not in case:
            errors.append(f"Missing required field: {field}")

    case_id = case.get("id", "<missing>")

    if "id" in case and not isinstance(case["id"], str):
        errors.append(f"[{case_id}] 'id' must be a string")

    if "question" in case and not isinstance(case["question"], str):
        errors.append(f"[{case_id}] 'question' must be a string")

    if "expected_tools" in case:
        if not isinstance(case["expected_tools"], list):
            errors.append(f"[{case_id}] 'expected_tools' must be a list")
        else:
            for tool in case["expected_tools"]:
                if tool not in VALID_TOOLS:
                    errors.append(f"[{case_id}] Unknown tool: '{tool}'. Valid: {sorted(VALID_TOOLS)}")

    if "category" in case and case["category"] not in VALID_CATEGORIES:
        errors.append(f"[{case_id}] Unknown category: '{case['category']}'. Valid: {sorted(VALID_CATEGORIES)}")

    if "difficulty" in case and case["difficulty"] not in VALID_DIFFICULTIES:
        errors.append(f"[{case_id}] Unknown difficulty: '{case['difficulty']}'. Valid: {sorted(VALID_DIFFICULTIES)}")

    if "ground_truth" in case and isinstance(case["ground_truth"], list):
        for i, gt in enumerate(case["ground_truth"]):
            if not isinstance(gt, dict):
                errors.append(f"[{case_id}] ground_truth[{i}] must be a dict")
                continue
            if "label" not in gt:
                errors.append(f"[{case_id}] ground_truth[{i}] missing 'label'")
            if "expected_pct" not in gt:
                errors.append(f"[{case_id}] ground_truth[{i}] missing 'expected_pct'")

    if "max_rounds" in case and (not isinstance(case["max_rounds"], int) or case["max_rounds"] < 1):
        errors.append(f"[{case_id}] 'max_rounds' must be a positive integer")

    if "max_cost_usd" in case and (not isinstance(case["max_cost_usd"], (int, float)) or case["max_cost_usd"] <= 0):
        errors.append(f"[{case_id}] 'max_cost_usd' must be a positive number")

    if "session_history" in case and isinstance(case["session_history"], list):
        for i, msg in enumerate(case["session_history"]):
            if not isinstance(msg, dict):
                errors.append(f"[{case_id}] session_history[{i}] must be a dict")
            elif "role" not in msg or "content" not in msg:
                errors.append(f"[{case_id}] session_history[{i}] missing 'role' or 'content'")

    return errors


def load_all_case_ids() -> set[str]:
    """Load all existing case IDs across all case files."""
    ids = set()
    for filename in CASE_SETS.values():
        path = _CASES_DIR / filename
        if path.exists():
            with open(path) as f:
                for case in json.load(f):
                    ids.add(case["id"])
    return ids


def check_id_uniqueness(case_id: str, exclude_file: str | None = None) -> str | None:
    """Check if a case ID is unique. Returns error string or None."""
    for name, filename in CASE_SETS.items():
        if exclude_file and filename == exclude_file:
            continue
        path = _CASES_DIR / filename
        if path.exists():
            with open(path) as f:
                for case in json.load(f):
                    if case["id"] == case_id:
                        return f"Duplicate ID '{case_id}' already exists in {name} ({filename})"
    return None


# ---------------------------------------------------------------------------
# Validate files
# ---------------------------------------------------------------------------

def validate_file(path: Path) -> int:
    """Validate all cases in a JSON file. Returns error count."""
    with open(path) as f:
        cases = json.load(f)

    if not isinstance(cases, list):
        print(f"  ERROR: File must contain a JSON array, got {type(cases).__name__}")
        return 1

    total_errors = 0
    seen_ids = set()

    for case in cases:
        case_id = case.get("id", "<missing>")

        # Check for duplicates within the file
        if case_id in seen_ids:
            print(f"  ERROR: Duplicate ID '{case_id}' within file")
            total_errors += 1
        seen_ids.add(case_id)

        errors = validate_case(case)
        for e in errors:
            print(f"  ERROR: {e}")
            total_errors += 1

    if total_errors == 0:
        print(f"  OK: {len(cases)} cases, all valid")
    else:
        print(f"  {total_errors} error(s) in {len(cases)} cases")

    return total_errors


def validate_all() -> int:
    """Validate all known case files. Returns total error count."""
    total = 0
    # Also check cross-file ID uniqueness
    all_ids: dict[str, str] = {}

    for name, filename in CASE_SETS.items():
        path = _CASES_DIR / filename
        print(f"\n--- {name}: {filename} ---")
        if not path.exists():
            print(f"  SKIP: file not found")
            continue
        total += validate_file(path)

        with open(path) as f:
            for case in json.load(f):
                cid = case["id"]
                if cid in all_ids:
                    print(f"  ERROR: ID '{cid}' duplicated across {all_ids[cid]} and {name}")
                    total += 1
                all_ids[cid] = name

    print(f"\n{'=' * 40}")
    print(f"Total: {len(all_ids)} cases across {len(CASE_SETS)} sets, {total} error(s)")
    return total


# ---------------------------------------------------------------------------
# Interactive case builder
# ---------------------------------------------------------------------------

def _prompt(label: str, default: str = "", required: bool = False) -> str:
    """Prompt for a string value."""
    suffix = f" [{default}]" if default else ""
    suffix += " (required)" if required else ""
    val = input(f"  {label}{suffix}: ").strip()
    if not val and default:
        return default
    if not val and required:
        print("    This field is required.")
        return _prompt(label, default, required)
    return val


def _prompt_list(label: str) -> list[str]:
    """Prompt for a comma-separated list."""
    val = input(f"  {label} (comma-separated, or empty): ").strip()
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


def _prompt_choice(label: str, choices: set[str], default: str = "") -> str:
    """Prompt for a value from a fixed set of choices."""
    sorted_choices = sorted(choices)
    suffix = f" [{default}]" if default else ""
    val = input(f"  {label} ({', '.join(sorted_choices)}){suffix}: ").strip()
    if not val and default:
        return default
    if val not in choices:
        print(f"    Invalid. Choose from: {sorted_choices}")
        return _prompt_choice(label, choices, default)
    return val


def _prompt_int(label: str, default: int | None = None) -> int | None:
    """Prompt for an integer."""
    suffix = f" [{default}]" if default is not None else " (or empty to skip)"
    val = input(f"  {label}{suffix}: ").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        print("    Must be an integer.")
        return _prompt_int(label, default)


def _prompt_float(label: str, default: float | None = None) -> float | None:
    """Prompt for a float."""
    suffix = f" [{default}]" if default is not None else " (or empty to skip)"
    val = input(f"  {label}{suffix}: ").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        print("    Must be a number.")
        return _prompt_float(label, default)


def build_case_interactive() -> dict:
    """Walk through interactive prompts to build a case dict."""
    print("\n=== New Benchmark Case ===\n")

    case = {}
    case["id"] = _prompt("Case ID (e.g. V3_31_description)", required=True)
    case["category"] = _prompt_choice("Category", VALID_CATEGORIES)
    case["difficulty"] = _prompt_choice("Difficulty", VALID_DIFFICULTIES, default="medium")
    case["description"] = _prompt("Description")
    case["question"] = _prompt("Question (the user query)", required=True)

    print("\n  --- Tools & Actions ---")
    tools = _prompt_list("Expected tools")
    case["expected_tools"] = tools
    actions = _prompt_list("Expected actions")
    if actions:
        case["expected_actions"] = actions

    print("\n  --- Keywords ---")
    case["must_contain"] = _prompt_list("Must contain keywords")
    case["must_not_contain"] = _prompt_list("Must NOT contain keywords")

    print("\n  --- Budgets ---")
    mr = _prompt_int("Max rounds", default=6)
    if mr:
        case["max_rounds"] = mr
    mc = _prompt_float("Max cost USD", default=0.15)
    if mc:
        case["max_cost_usd"] = mc

    print("\n  --- Ground Truth ---")
    case["ground_truth"] = []
    while True:
        label = _prompt("Ground truth label (empty to stop)")
        if not label:
            break
        pct = _prompt_float(f"Expected % for '{label}'")
        tol = _prompt_float("Tolerance", default=2.0)
        if pct is not None:
            entry = {"label": label, "expected_pct": pct}
            if tol is not None:
                entry["tolerance"] = tol
            case["ground_truth"].append(entry)

    case["ground_truth_notes"] = _prompt("Ground truth notes")

    return case


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Add or validate benchmark cases for GeoNatureAgent Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target", default="v3",
        help=f"Case set to append to ({', '.join(CASE_SETS.keys())}). Default: v3",
    )
    parser.add_argument(
        "--validate", metavar="FILE",
        help="Validate a single case file (no modifications)",
    )
    parser.add_argument(
        "--validate-all", action="store_true",
        help="Validate all known case files",
    )
    parser.add_argument(
        "--import", dest="import_file", metavar="FILE",
        help="Import case(s) from a JSON file and append to --target",
    )
    args = parser.parse_args()

    # Validate modes
    if args.validate:
        path = Path(args.validate)
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        print(f"Validating: {path}")
        errors = validate_file(path)
        sys.exit(1 if errors else 0)

    if args.validate_all:
        errors = validate_all()
        sys.exit(1 if errors else 0)

    # Resolve target file
    target_filename = CASE_SETS.get(args.target)
    if not target_filename:
        print(f"Unknown target set: {args.target}. Available: {list(CASE_SETS.keys())}")
        sys.exit(1)
    target_path = _CASES_DIR / target_filename

    # Import mode
    if args.import_file:
        import_path = Path(args.import_file)
        if not import_path.exists():
            print(f"Import file not found: {import_path}")
            sys.exit(1)

        with open(import_path) as f:
            imported = json.load(f)

        if isinstance(imported, dict):
            imported = [imported]

        existing_ids = load_all_case_ids()
        valid_cases = []

        for case in imported:
            errors = validate_case(case)
            if errors:
                print(f"Validation errors for '{case.get('id', '?')}':")
                for e in errors:
                    print(f"  {e}")
                continue
            if case["id"] in existing_ids:
                print(f"Skipping duplicate ID: {case['id']}")
                continue
            valid_cases.append(case)

        if not valid_cases:
            print("No valid cases to import.")
            sys.exit(1)

        # Load existing and append
        existing = []
        if target_path.exists():
            with open(target_path) as f:
                existing = json.load(f)

        existing.extend(valid_cases)
        with open(target_path, "w") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
            f.write("\n")

        print(f"Imported {len(valid_cases)} case(s) into {args.target} ({target_path})")
        sys.exit(0)

    # Interactive mode
    case = build_case_interactive()

    # Validate
    errors = validate_case(case)
    if errors:
        print("\nValidation errors:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    # Check uniqueness
    dup = check_id_uniqueness(case["id"])
    if dup:
        print(f"\n{dup}")
        sys.exit(1)

    # Preview
    print(f"\n--- Preview ---")
    print(json.dumps(case, indent=2, ensure_ascii=False))

    confirm = input("\nAppend to {args.target}? [y/N] ").strip().lower()
    if confirm != "y":
        # Still save to stdout
        print("\nCase JSON (not saved):")
        print(json.dumps(case, indent=2, ensure_ascii=False))
        sys.exit(0)

    # Append
    existing = []
    if target_path.exists():
        with open(target_path) as f:
            existing = json.load(f)

    existing.append(case)
    with open(target_path, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Saved to {target_path} ({len(existing)} cases total)")


if __name__ == "__main__":
    main()