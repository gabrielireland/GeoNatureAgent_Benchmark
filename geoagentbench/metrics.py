"""Model-aware cost calculation, accuracy aggregation, and error taxonomy.

Replaces the hardcoded Sonnet pricing in the old run_eval.py.
"""

from typing import Dict, List, Optional

from geoagentbench.scoring import ScoredResult

# Pricing per 1M tokens (USD). Update when models change.
PRICING: Dict[str, Dict[str, float]] = {
    # Anthropic (direct API & Vertex AI)
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "vertex_ai/claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    # Google Gemini (Vertex AI)
    "vertex_ai/gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "vertex_ai/gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "vertex_ai/gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    # Meta Llama 4 (Vertex AI MaaS)
    "vertex_ai/meta/llama-4-scout-17b-16e-instruct-maas": {"input": 0.17, "output": 0.66},
    "vertex_ai/meta/llama-4-maverick-17b-128e-instruct-maas": {"input": 0.17, "output": 0.66},
    # DeepSeek (Vertex AI MaaS)
    "vertex_ai/deepseek-ai/deepseek-v3.2-maas": {"input": 0.27, "output": 1.10},
    "vertex_ai/deepseek-ai/deepseek-r1-0528-maas": {"input": 0.55, "output": 2.19},
    # OpenAI open-source (Vertex AI MaaS)
    "vertex_ai/openai/gpt-oss-120b-maas": {"input": 3.0, "output": 15.0},
    "vertex_ai/openai/gpt-oss-20b-maas": {"input": 0.50, "output": 2.0},
    # ZAI GLM (Vertex AI MaaS)
    "vertex_ai/zai-org/glm-5-maas": {"input": 1.0, "output": 4.0},
    # Qwen (Vertex AI MaaS)
    "vertex_ai/qwen/qwen3-235b-a22b-instruct-2507-maas": {"input": 0.30, "output": 1.20},
}

# Fallback pricing when model not in PRICING table
_DEFAULT_PRICING = {"input": 3.0, "output": 15.0}


def compute_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a single query."""
    pricing = PRICING.get(model_id, _DEFAULT_PRICING)
    return (
        input_tokens * pricing["input"] / 1_000_000
        + output_tokens * pricing["output"] / 1_000_000
    )


def accuracy_by_category(results: List[ScoredResult]) -> Dict[str, Dict[str, int]]:
    """Compute pass/fail counts grouped by case category."""
    categories: Dict[str, Dict[str, int]] = {}
    for r in results:
        cat = r.metadata.get("category", "uncategorized")
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0, "failed": 0}
        categories[cat]["total"] += 1
        if r.passed:
            categories[cat]["passed"] += 1
        else:
            categories[cat]["failed"] += 1
    return categories


def difficulty_weighted_accuracy(results: List[ScoredResult]) -> Optional[float]:
    """Accuracy weighted by case difficulty: easy=1, medium=2, hard=3 (metric J).

    Returns None when no results have a recognised difficulty tag.
    """
    _WEIGHTS = {"easy": 1, "medium": 2, "hard": 3}
    weighted_sum = 0.0
    weight_total = 0
    for r in results:
        w = _WEIGHTS.get((r.metadata or {}).get("difficulty", ""), 1)
        weighted_sum += w * (1 if r.passed else 0)
        weight_total += w
    if weight_total == 0:
        return None
    return round(weighted_sum / weight_total, 4)


def accuracy_by_difficulty(results: List[ScoredResult]) -> Dict[str, Dict]:
    """Pass rate and avg check_score grouped by difficulty tier (metric J)."""
    groups: Dict[str, Dict] = {}
    for r in results:
        diff = (r.metadata or {}).get("difficulty", "") or "unknown"
        if diff not in groups:
            groups[diff] = {"total": 0, "passed": 0, "failed": 0, "check_scores": []}
        groups[diff]["total"] += 1
        if r.passed:
            groups[diff]["passed"] += 1
        else:
            groups[diff]["failed"] += 1
        groups[diff]["check_scores"].append(r.check_score)

    return {
        diff: {
            "total": g["total"],
            "passed": g["passed"],
            "failed": g["failed"],
            "pass_rate": round(g["passed"] / g["total"], 4) if g["total"] else 0.0,
            "avg_check_score": round(sum(g["check_scores"]) / len(g["check_scores"]), 4),
        }
        for diff, g in groups.items()
    }


def cost_accuracy_summary(results: List[ScoredResult]) -> Dict[str, float]:
    """Compute aggregate cost, accuracy, and efficiency metrics."""
    if not results:
        return {"accuracy": 0.0, "total_cost_usd": 0.0, "cost_per_case_usd": 0.0}

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    total_cost = sum(r.cost_usd for r in results)

    util_rounds = [r.rounds_utilization for r in results if r.rounds_utilization is not None]
    util_cost = [r.cost_utilization for r in results if r.cost_utilization is not None]
    kw_coverages = [r.keyword_coverage for r in results if r.keyword_coverage is not None]
    tool_f1s = [r.tool_f1 for r in results if r.tool_f1 is not None]
    ms_per_rounds = [r.ms_per_round for r in results if r.ms_per_round is not None]

    return {
        "accuracy": passed / total if total else 0.0,
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "total_cost_usd": round(total_cost, 4),
        "cost_per_case_usd": round(total_cost / total, 4) if total else 0.0,
        "total_input_tokens": sum(r.input_tokens for r in results),
        "total_output_tokens": sum(r.output_tokens for r in results),
        "total_duration_ms": sum(r.duration_ms for r in results),
        "avg_rounds_utilization": round(sum(util_rounds) / len(util_rounds), 3) if util_rounds else None,
        "avg_cost_utilization": round(sum(util_cost) / len(util_cost), 3) if util_cost else None,
        "cases_near_limit_count": sum(
            1 for r in results
            if (r.rounds_utilization or 0) > 0.8 or (r.cost_utilization or 0) > 0.8
        ),
        # Metric F: partial credit
        "avg_check_score": round(sum(r.check_score for r in results) / total, 4),
        "avg_quality_check_score": round(sum(r.quality_check_score for r in results) / total, 4),
        # Metric G: keyword coverage
        "avg_keyword_coverage": round(sum(kw_coverages) / len(kw_coverages), 4) if kw_coverages else None,
        # Metric H: tool F1
        "avg_tool_f1": round(sum(tool_f1s) / len(tool_f1s), 4) if tool_f1s else None,
        # Metric I: latency per round
        "avg_ms_per_round": round(sum(ms_per_rounds) / len(ms_per_rounds), 1) if ms_per_rounds else None,
        # Metric J: difficulty-weighted accuracy
        "difficulty_weighted_accuracy": difficulty_weighted_accuracy(results),
    }


def check_type_accuracy(results: List[ScoredResult]) -> Dict[str, float]:
    """Pass rate per check type across all cases (metric E).

    Extracts the check type from each check's 'check' field using prefix matching
    and returns {type: pass_rate} rounded to 3 decimal places.
    """
    _PREFIXES = [
        ("expected_tools", "expected_tools"),
        ("chart_generated", "chart_generated"),
        ("numeric_accuracy", "numeric_accuracy"),
        ("must_contain", "must_contain"),
        ("must_not_contain", "must_not_contain"),
        ("max_rounds", "max_rounds"),
        ("cost", "cost_budget"),
        ("expected_actions", "expected_actions"),
    ]

    totals: Dict[str, int] = {}
    passed_counts: Dict[str, int] = {}

    for result in results:
        for check in result.checks:
            check_name = check.get("check", "")
            check_type = None
            for prefix, key in _PREFIXES:
                if check_name == prefix or check_name.startswith(f"{prefix}:") or check_name.startswith(f"{prefix} "):
                    check_type = key
                    break
            if check_type is None:
                continue
            totals[check_type] = totals.get(check_type, 0) + 1
            if check.get("passed"):
                passed_counts[check_type] = passed_counts.get(check_type, 0) + 1

    return {
        k: round(passed_counts.get(k, 0) / v, 3)
        for k, v in totals.items()
    }


def build_error_taxonomy(results: List[ScoredResult]) -> Dict[str, int]:
    """Count error categories from scored results.

    Error categories are assigned post-hoc during human evaluation.
    This function aggregates whatever categories have been set.
    """
    taxonomy: Dict[str, int] = {}
    for r in results:
        if not r.passed and r.error_category:
            taxonomy[r.error_category] = taxonomy.get(r.error_category, 0) + 1
    return taxonomy
