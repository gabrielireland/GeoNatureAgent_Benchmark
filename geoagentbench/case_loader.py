"""Load and validate benchmark cases from JSON files."""

import json
from pathlib import Path
from typing import List, Optional

_CASES_DIR = Path(__file__).parent / "cases"

# Named case sets mapping to JSON files
CASE_SETS = {
    "dev": "dev.json",
    "v5": "benchmark_v5.json",
}


def load_cases(
    case_set: str = "dev",
    case_file: Optional[str] = None,
    filter_ids: Optional[List[str]] = None,
    filter_categories: Optional[List[str]] = None,
) -> list:
    """Load benchmark cases from a named set or custom JSON file.

    Args:
        case_set: Named set ('dev', 'v1', 'v2', 'all'). Ignored if case_file is set.
        case_file: Path to a custom JSON cases file.
        filter_ids: Only include cases with these IDs.
        filter_categories: Only include cases in these categories.

    Returns:
        List of case dicts.
    """
    if case_file:
        path = Path(case_file)
    elif case_set == "all":
        cases = []
        for name in CASE_SETS.values():
            path = _CASES_DIR / name
            if path.exists():
                with open(path) as f:
                    cases.extend(json.load(f))
        return _filter_cases(cases, filter_ids, filter_categories)
    else:
        filename = CASE_SETS.get(case_set)
        if not filename:
            raise ValueError(f"Unknown case set: {case_set}. Available: {list(CASE_SETS.keys())}")
        path = _CASES_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Case file not found: {path}")

    with open(path) as f:
        cases = json.load(f)

    return _filter_cases(cases, filter_ids, filter_categories)


def _filter_cases(
    cases: list,
    filter_ids: Optional[List[str]] = None,
    filter_categories: Optional[List[str]] = None,
) -> list:
    """Filter cases by ID and/or category."""
    if filter_ids:
        cases = [c for c in cases if c["id"] in filter_ids]
    if filter_categories:
        cases = [c for c in cases if c.get("category") in filter_categories]
    return cases
