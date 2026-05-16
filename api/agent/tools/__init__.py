"""Tool registry and execution dispatcher.

Central entry point for all agent tool calls. Handles:
- Pydantic validation of tool inputs
- Dispatching to the correct executor function
- Logging tool calls and results
"""

import json
import logging
from typing import Any, Dict, Optional

from pydantic import ValidationError

from agent.tools.models import TOOL_INPUT_MODELS
from agent.tools.executors import (
    exec_list_layers,
    exec_get_legend,
    exec_analyze_area,
    exec_get_layer_bounds,
    exec_lookup_province,
    exec_lookup_municipality,
    exec_toggle_layer,
    exec_compare_areas,
    exec_find_top_n,
    exec_generate_chart,
    exec_analyze_multi_layer,
    exec_query_erosion_stats,
    exec_create_buffer,
    exec_select_features_by_spatial_relationship,
    exec_get_centroids,
    exec_reject_task,
)

logger = logging.getLogger(__name__)


def execute_tool(
    name: str, input_data: Dict[str, Any], cache_manager, user: Optional[Dict] = None,
) -> str:
    """Execute a tool call from the LLM. Returns JSON string."""
    # Log what the LLM is asking for (omit AOI coords to keep logs readable)
    log_input = {k: v for k, v in input_data.items() if k != "aoi"}
    if "aoi" in input_data:
        aoi = input_data["aoi"]
        log_input["aoi_type"] = aoi.get("type", "unknown") if isinstance(aoi, dict) else type(aoi).__name__
        coords = (aoi.get("coordinates") or [[]])[0] if isinstance(aoi, dict) else []
        log_input["aoi_num_points"] = len(coords) if isinstance(coords, list) else 0
    logger.info("[AGENT] Tool call: %s | Input: %s", name, json.dumps(log_input, ensure_ascii=False))

    # Pydantic validation — catch malformed inputs before dispatch
    model_cls = TOOL_INPUT_MODELS.get(name)
    if model_cls:
        try:
            model_cls(**input_data)
        except ValidationError as ve:
            errors = "; ".join(
                f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in ve.errors()
            )
            hint = f"Validation failed for {name}: {errors}. Please retry with correct parameters."
            logger.warning("[AGENT] Validation error for %s: %s", name, errors)
            return json.dumps({"error": hint, "hint": "Check required fields and types, then retry."})

    try:
        if name == "list_layers":
            result = exec_list_layers(cache_manager, user)
        elif name == "get_legend":
            result = exec_get_legend(input_data["indicator"])
        elif name == "analyze_area":
            result = exec_analyze_area(
                input_data["indicator"], input_data["year"], input_data["season"],
                input_data["aoi"], cache_manager, user,
            )
        elif name == "get_layer_bounds":
            result = exec_get_layer_bounds(
                input_data["indicator"], input_data["year"], input_data["season"],
                cache_manager,
            )
        elif name == "lookup_province":
            result = exec_lookup_province(input_data["name"])
        elif name == "lookup_municipality":
            result = exec_lookup_municipality(
                input_data["name"], input_data.get("province", ""),
            )
        elif name == "toggle_layer":
            result = exec_toggle_layer(
                input_data["indicator"], input_data.get("visible", True), cache_manager,
            )
        elif name == "compare_areas":
            result = exec_compare_areas(
                input_data["area_a"], input_data["area_b"],
                input_data["indicator"], input_data["year"], input_data["season"],
                cache_manager, user,
            )
        elif name == "find_top_n":
            result = exec_find_top_n(
                input_data["metric"],
                input_data.get("n", 10),
                input_data.get("order", "desc"),
                input_data.get("filter_provinces") or None,
            )
        elif name == "generate_chart":
            result = exec_generate_chart(
                input_data["chart_type"],
                input_data["title"],
                input_data["data"],
                input_data.get("x_label", ""),
                input_data.get("y_label", ""),
                input_data.get("output_prefix", "poc/charts"),
                input_data.get("filename", ""),
            )
        elif name == "analyze_multi_layer":
            result = exec_analyze_multi_layer(
                input_data["province"],
                input_data["indicators"],
                cache_manager, user,
            )
        elif name == "query_erosion_stats":
            result = exec_query_erosion_stats(
                input_data["query_type"],
                input_data["indices"],
                input_data.get("municipality", ""),
                input_data.get("year_start", 2018),
                input_data.get("year_end", 2025),
            )
        elif name == "create_buffer":
            result = exec_create_buffer(
                input_data["area_name"],
                input_data["buffer_km"],
                input_data.get("area_type", "province"),
                input_data.get("province_hint", ""),
            )
        elif name == "select_features_by_spatial_relationship":
            result = exec_select_features_by_spatial_relationship(
                input_data["target_type"],
                input_data["spatial_predicates"],
                input_data.get("reference_area", ""),
                input_data.get("reference_type", "province"),
                input_data.get("reference_aoi"),
                input_data.get("province_hint", ""),
            )
        elif name == "get_centroids":
            result = exec_get_centroids(
                input_data["area_names"],
                input_data.get("area_type", "province"),
                input_data.get("province_hint", ""),
            )
        elif name == "reject_task":
            result = exec_reject_task(input_data["reason"])
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        logger.exception("[AGENT] Tool execution error: %s", name)
        result = {"error": str(exc)}

    result_str = json.dumps(result, ensure_ascii=False)
    if "error" in result:
        logger.error("[AGENT] Tool %s FAILED: %s", name, result.get("error"))
    else:
        preview = result_str[:500] + "..." if len(result_str) > 500 else result_str
        logger.info("[AGENT] Tool %s OK: %s", name, preview)

    return result_str
