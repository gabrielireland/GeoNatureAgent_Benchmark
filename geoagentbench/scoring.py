"""Eval scoring — checks agent output against case expectations.

Extracted and extended from the inline check logic in run_eval.py.
Each check function returns a list of check results (dicts with 'check', 'passed', and details).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScoredResult:
    """Structured result for a single evaluated case."""

    case_id: str
    description: str
    passed: bool
    duration_ms: int
    rounds: int
    tools_used: List[str]
    actions: List[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    answer_preview: str
    checks: List[Dict[str, Any]]
    error: Optional[str] = None
    error_category: Optional[str] = None
    rounds_utilization: Optional[float] = None
    cost_utilization: Optional[float] = None
    # Metric F: partial credit scores
    check_score: float = 1.0               # n_checks_passed / n_checks_total
    quality_check_score: float = 1.0       # quality checks only (tools/actions/keywords/numeric)
    # Metric G: keyword coverage fraction
    keyword_coverage: Optional[float] = None
    # Metric H: tool set F1 (precision, recall, F1 on unique tools)
    tool_precision: Optional[float] = None
    tool_recall: Optional[float] = None
    tool_f1: Optional[float] = None
    # Metric H2: action set F1
    action_precision: Optional[float] = None
    action_recall: Optional[float] = None
    action_f1: Optional[float] = None
    # Metric I: latency per round
    ms_per_round: Optional[float] = None
    # Metric I2: answer verbosity
    answer_chars: int = 0
    # Full Q&A traceability (paper-ready)
    full_answer: str = ""
    question: str = ""
    tools_called: List[Dict[str, Any]] = field(default_factory=list)
    conversation_trace: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def check_expected_tools(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that the agent called the expected tools."""
    if "expected_tools" not in case:
        return []

    expected = set(case["expected_tools"])
    raw_tools = agent_output.get("tools_used", [])
    tools_used = [t["tool"] if isinstance(t, dict) else t for t in raw_tools]
    actual = set(tools_used)
    missing = expected - actual

    return [{
        "check": "expected_tools",
        "passed": len(missing) == 0,
        "expected": sorted(expected),
        "actual": sorted(actual),
        "missing": sorted(missing) if missing else None,
    }]


def check_expected_actions(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that the agent generated the expected frontend actions."""
    if "expected_actions" not in case:
        return []

    expected = set(case["expected_actions"])
    raw_actions = agent_output.get("actions", [])
    actions = [a["type"] if isinstance(a, dict) else a for a in raw_actions]
    actual = set(actions)
    missing = expected - actual

    return [{
        "check": "expected_actions",
        "passed": len(missing) == 0,
        "expected": sorted(expected),
        "actual": sorted(actual),
        "missing": sorted(missing) if missing else None,
    }]


def check_must_contain(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that the response contains required keywords."""
    answer = (agent_output.get("answer") or "").lower()
    checks = []
    for keyword in case.get("must_contain", []):
        checks.append({
            "check": f"must_contain: '{keyword}'",
            "passed": keyword.lower() in answer,
        })
    return checks


def check_must_not_contain(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that the response does NOT contain forbidden keywords."""
    answer = (agent_output.get("answer") or "").lower()
    checks = []
    for keyword in case.get("must_not_contain", []):
        checks.append({
            "check": f"must_not_contain: '{keyword}'",
            "passed": keyword.lower() not in answer,
        })
    return checks


def check_max_rounds(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that tool-use rounds stayed within limit."""
    max_rounds = case.get("max_rounds")
    if not max_rounds:
        return []

    usage = agent_output.get("usage", {})
    actual_rounds = usage.get("rounds", 0)
    if actual_rounds <= 0:
        return []

    return [{
        "check": f"max_rounds <= {max_rounds}",
        "passed": actual_rounds <= max_rounds,
        "actual_rounds": actual_rounds,
    }]


def check_cost_budget(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that the query stayed within cost budget (if specified)."""
    max_cost = case.get("max_cost_usd")
    if max_cost is None:
        return []

    cost = agent_output.get("_cost_usd", 0.0)
    return [{
        "check": f"cost <= ${max_cost}",
        "passed": cost <= max_cost,
        "actual_cost": cost,
    }]


def check_latency_budget(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that the query completed within latency budget (if specified)."""
    max_latency = case.get("max_latency_ms")
    if max_latency is None:
        return []

    latency = agent_output.get("_duration_ms", 0)
    return [{
        "check": f"latency <= {max_latency}ms",
        "passed": latency <= max_latency,
        "actual_latency_ms": latency,
    }]


def check_chart_generated(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that generate_chart produced at least one chart URL (metric B)."""
    if "generate_chart" not in case.get("expected_tools", []):
        return []
    chart_urls = agent_output.get("chart_urls", [])
    return [{
        "check": "chart_generated",
        "passed": len(chart_urls) > 0,
        "chart_urls": chart_urls if chart_urls else None,
    }]


def check_numeric_accuracy(case: dict, agent_output: dict) -> List[Dict[str, Any]]:
    """Check that numeric values in the answer match ground truth within tolerance (metric A).

    Case schema:
        "ground_truth": [
            {"label": "Ciudad Real", "expected_pct": 78.9, "tolerance": 2.0},
            ...
        ]
    Extraction: finds the label in the answer, then searches the next 120 chars
    for the first float followed by '%'.
    """
    ground_truth = case.get("ground_truth")
    if not ground_truth:
        return []

    answer = agent_output.get("answer") or ""
    checks = []
    for entry in ground_truth:
        label = entry["label"]
        expected = float(entry["expected_pct"])
        tolerance = float(entry.get("tolerance", 2.0))

        label_pos = answer.lower().find(label.lower())
        if label_pos == -1:
            checks.append({
                "check": f"numeric_accuracy: '{label}'",
                "passed": False,
                "expected_pct": expected,
                "found_pct": None,
                "note": "label_not_found",
            })
            continue

        window = answer[label_pos:label_pos + 120]
        match = re.search(r"(\d+\.?\d*)\s*%", window)
        if not match:
            checks.append({
                "check": f"numeric_accuracy: '{label}'",
                "passed": False,
                "expected_pct": expected,
                "found_pct": None,
                "note": "no_value_found",
            })
            continue

        found = float(match.group(1))
        passed = abs(found - expected) <= tolerance
        checks.append({
            "check": f"numeric_accuracy: '{label}'",
            "passed": passed,
            "expected_pct": expected,
            "found_pct": found,
            "tolerance": tolerance,
        })

    return checks


_QUALITY_PREFIXES = {
    "expected_tools",
    "expected_actions",
    "chart_generated",
    "must_contain",
    "must_not_contain",
    "numeric_accuracy",
}


def _compute_check_scores(checks: List[Dict[str, Any]]) -> tuple:
    """Return (check_score, quality_check_score) as floats in [0.0, 1.0].

    check_score        = all checks passed / all checks total
    quality_check_score = quality checks passed / quality checks total
    Both default to 1.0 when there are no checks of that type.
    """
    if not checks:
        return 1.0, 1.0

    all_passed = sum(1 for c in checks if c.get("passed"))
    all_total = len(checks)

    quality_passed = 0
    quality_total = 0
    for c in checks:
        name = c.get("check", "")
        is_quality = any(
            name == p or name.startswith(f"{p}:") or name.startswith(f"{p} ")
            for p in _QUALITY_PREFIXES
        )
        if is_quality:
            quality_total += 1
            if c.get("passed"):
                quality_passed += 1

    check_score = round(all_passed / all_total, 4)
    quality_check_score = round(quality_passed / quality_total, 4) if quality_total else 1.0
    return check_score, quality_check_score


def _compute_set_f1(
    expected: List[str], actual: List[str]
) -> tuple:
    """Compute precision, recall, F1 on unique-element sets.

    Returns (precision, recall, f1) as floats rounded to 4 decimal places,
    or (None, None, None) when expected is empty (check not defined for this case).
    """
    if not expected:
        return None, None, None
    exp_set = set(expected)
    act_set = set(actual)
    intersection = exp_set & act_set

    recall = len(intersection) / len(exp_set)
    precision = len(intersection) / len(act_set) if act_set else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return round(precision, 4), round(recall, 4), round(f1, 4)


def _auto_classify_error(checks: List[Dict[str, Any]], agent_output: dict) -> Optional[str]:
    """Return an error category string based on the first failing check (metric C)."""
    if agent_output.get("error") and not any(c for c in checks if c.get("passed")):
        return "agent_error"

    priority = [
        ("expected_tools", "tool_missing"),
        ("chart_generated", "chart_missing"),
        ("numeric_accuracy", "wrong_data"),
        ("max_rounds", "rounds_exceeded"),
        ("cost", "cost_exceeded"),
        ("must_contain", "keyword_missing"),
        ("must_not_contain", "forbidden_keyword"),
        ("latency", "latency_exceeded"),
    ]
    for check in checks:
        if check.get("passed"):
            continue
        check_name = check.get("check", "")
        for prefix, category in priority:
            if check_name == prefix or check_name.startswith(f"{prefix}:") or check_name.startswith(f"{prefix} "):
                return category
    return None


def score_result(case: dict, agent_output: dict, duration_ms: int, cost_usd: float, question: str = "") -> ScoredResult:
    """Run all checks for a case and return a structured ScoredResult."""
    checks = []
    checks += check_expected_tools(case, agent_output)
    checks += check_expected_actions(case, agent_output)
    checks += check_chart_generated(case, agent_output)
    checks += check_must_contain(case, agent_output)
    checks += check_must_not_contain(case, agent_output)
    checks += check_numeric_accuracy(case, agent_output)
    checks += check_max_rounds(case, agent_output)

    agent_output["_cost_usd"] = cost_usd
    agent_output["_duration_ms"] = duration_ms
    checks += check_cost_budget(case, agent_output)
    checks += check_latency_budget(case, agent_output)

    all_passed = all(c["passed"] for c in checks)
    usage = agent_output.get("usage", {})
    tools_used = [t["tool"] for t in agent_output.get("tools_used", [])]
    actions = [a["type"] for a in agent_output.get("actions", [])]

    # Metric C: auto-classify failure reason
    error_category = None if all_passed else _auto_classify_error(checks, agent_output)

    # Metric D: efficiency utilization (continuous 0.0–1.0+)
    rounds_utilization = None
    cost_utilization = None
    actual_rounds = usage.get("rounds", 0)
    max_rounds = case.get("max_rounds")
    if max_rounds and actual_rounds > 0:
        rounds_utilization = round(actual_rounds / max_rounds, 3)
    max_cost = case.get("max_cost_usd")
    if max_cost and cost_usd > 0:
        cost_utilization = round(cost_usd / max_cost, 3)

    # Metric F: partial credit scores
    check_score, quality_check_score = _compute_check_scores(checks)

    # Metric G: keyword coverage fraction
    kw_checks = [c for c in checks if c.get("check", "").startswith("must_contain:")]
    keyword_coverage = (
        round(sum(1 for c in kw_checks if c.get("passed")) / len(kw_checks), 4)
        if kw_checks else None
    )

    # Metric H: tool F1
    tool_precision, tool_recall, tool_f1 = _compute_set_f1(
        case.get("expected_tools", []), tools_used
    )

    # Metric H2: action F1
    action_precision, action_recall, action_f1 = _compute_set_f1(
        case.get("expected_actions", []), actions
    )

    # Metric I: latency per round
    ms_per_round = round(duration_ms / actual_rounds, 1) if actual_rounds > 0 else None

    # Metric I2: answer verbosity
    answer_chars = len(agent_output.get("answer") or "")

    # Preserve full tool dicts (with inputs) from agent output
    raw_tools = agent_output.get("tools_used", [])
    tools_called_full = [t for t in raw_tools if isinstance(t, dict)]

    # Conversation trace (full LLM reasoning chain)
    conversation_trace = agent_output.get("conversation_trace", [])

    return ScoredResult(
        case_id=case["id"],
        description=case.get("description", ""),
        passed=all_passed,
        duration_ms=duration_ms,
        rounds=actual_rounds,
        tools_used=tools_used,
        actions=actions,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cost_usd=cost_usd,
        answer_preview=(agent_output.get("answer") or "")[:200],
        checks=checks,
        error=agent_output.get("error"),
        error_category=error_category,
        rounds_utilization=rounds_utilization,
        cost_utilization=cost_utilization,
        check_score=check_score,
        quality_check_score=quality_check_score,
        keyword_coverage=keyword_coverage,
        tool_precision=tool_precision,
        tool_recall=tool_recall,
        tool_f1=tool_f1,
        action_precision=action_precision,
        action_recall=action_recall,
        action_f1=action_f1,
        ms_per_round=ms_per_round,
        answer_chars=answer_chars,
        full_answer=agent_output.get("full_answer") or agent_output.get("answer") or "",
        question=question or case.get("question", ""),
        tools_called=tools_called_full,
        conversation_trace=conversation_trace,
    )
