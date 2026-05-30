"""GeoNatureAgent — Agentic Advisor

Main agent loop with tool-use orchestration. Features:
- Parallel tool execution (state-setting sequential, independent concurrent)
- Language detection for bilingual responses
- Input/output sanitization (security)
- Injectable LLM client (for benchmarks: AnthropicClient, LiteLLMClient)
- Municipality lookup support
- Structured report generation
- max_tokens continuation handling
- Auto-toggle of analyzed layers and contextual layers (burnt_areas, MFE)

Module layout (split from monolithic V1):
    agent.py          -- This file: main loop only
    security.py       -- Input/output sanitization, language detection
    session.py        -- Session store with TTL + eviction
    charts.py         -- Chart/report generation, CO2 methodology data
    tools/            -- Tool registry, Pydantic models, executor functions
"""

import concurrent.futures
import json
import logging
import os
import time as _time_mod
from typing import Any, Dict, List, Optional

import anthropic

from agent.charts import build_chart, build_report
from agent.security import detect_language, sanitize_input, sanitize_output
from agent.session import session_store
from agent.tools import execute_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Geometry helpers — delegate to darwin_geo_core canonical implementation
# ---------------------------------------------------------------------------

from agent.provinces import _compute_bounds as _bounds_from_geometry


# ---------------------------------------------------------------------------
# Load prompt + tool definitions from versioned files
# ---------------------------------------------------------------------------

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

PARALLEL_TOOLS_ENABLED = os.getenv("AGENT_PARALLEL_TOOLS", "true").lower() == "true"


def _load_prompt(version: str = None) -> str:
    """Load system prompt from api/agent/prompts/{version}.md"""
    version = version or os.getenv("AGENT_PROMPT_VERSION", "v3")
    prompt_path = os.path.join(_AGENT_DIR, "prompts", f"{version}.md")
    if not os.path.isfile(prompt_path):
        logger.error("[AGENT] Prompt file not found: %s -- falling back to v1", prompt_path)
        prompt_path = os.path.join(_AGENT_DIR, "prompts", "v1.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _load_tools() -> list:
    """Load tool definitions from api/agent/tools/tools.json"""
    tools_path = os.path.join(_AGENT_DIR, "tools", "tools.json")
    with open(tools_path, "r", encoding="utf-8") as f:
        return json.load(f)


SYSTEM_PROMPT = _load_prompt()
TOOLS = _load_tools()

logger.info(
    "[AGENT] Loaded prompt version '%s' (%d chars) and %d tools",
    os.getenv("AGENT_PROMPT_VERSION", "v3"), len(SYSTEM_PROMPT), len(TOOLS),
)


# ---------------------------------------------------------------------------
# Tool result processing helper
# ---------------------------------------------------------------------------


def _process_tool_result(
    block, tool_input: Dict, result_str: str,
    analysis_results: List[Dict], actions: List[Dict], tools_used: List[Dict],
    current_province_name: str, last_analyzed_layer_ref: List,
    chart_urls: List[str],
):
    """Process a single tool execution result: update tracking lists and queue actions.

    last_analyzed_layer_ref is a single-element list used as a mutable reference.
    """
    if block.name == "generate_chart":
        try:
            parsed = json.loads(result_str)
            if "gcs_uri" in parsed:
                chart_urls.append(parsed["gcs_uri"])
        except (json.JSONDecodeError, TypeError):
            pass

    if block.name == "analyze_area":
        try:
            parsed = json.loads(result_str)
            label = tool_input.get("_province_name") or current_province_name or f"Area {len(analysis_results) + 1}"
            analysis_results.append({
                "label": label,
                "result": parsed,
                "tool_input": {
                    "indicator": tool_input.get("indicator", ""),
                    "year": tool_input.get("year", ""),
                    "season": tool_input.get("season", ""),
                },
            })
        except (json.JSONDecodeError, TypeError):
            pass

        analyzed_indicator = tool_input.get("indicator", "")
        if analyzed_indicator:
            last_analyzed_layer_ref[0] = {
                "indicator": analyzed_indicator,
                "year": tool_input.get("year", ""),
                "season": tool_input.get("season", ""),
            }

    if block.name == "toggle_layer":
        try:
            parsed = json.loads(result_str)
            if "error" not in parsed:
                actions.append({
                    "type": "toggle_layer",
                    "indicator": parsed["indicator"],
                    "year": parsed.get("year", ""),
                    "season": parsed.get("season", ""),
                    "visible": parsed.get("visible", True),
                    "display_name": parsed.get("display_name", ""),
                    "bounds": parsed.get("bounds"),
                })
        except (json.JSONDecodeError, TypeError):
            pass

    tools_used.append({"tool": block.name, "input": tool_input})


def _serialize_messages(messages: List[Dict]) -> List[Dict]:
    """Convert message content from Anthropic SDK objects to plain dicts for serialization."""
    out = []
    for msg in messages:
        content = msg.get("content")
        if content is None:
            out.append(msg)
        elif isinstance(content, str):
            out.append(msg)
        elif isinstance(content, list):
            serialized_content = []
            for item in content:
                if isinstance(item, dict):
                    serialized_content.append(item)
                elif hasattr(item, "model_dump"):
                    serialized_content.append(item.model_dump())
                elif hasattr(item, "__dict__"):
                    serialized_content.append(item.__dict__)
                else:
                    serialized_content.append(str(item))
            out.append({"role": msg["role"], "content": serialized_content})
        elif hasattr(content, "model_dump"):
            out.append({"role": msg["role"], "content": content.model_dump()})
        else:
            out.append(msg)
    return out


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

MAX_TOOL_ROUNDS = 10


def run_agent(
    question: str,
    aoi: Optional[Dict[str, Any]] = None,
    cache_manager=None,
    user: Optional[Dict] = None,
    session_id: Optional[str] = None,
    llm_client=None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the agent loop: send question to LLM, execute tools, return final answer.

    Args:
        llm_client: Optional injectable LLM client (for benchmarks). When None,
            uses the default Anthropic client (production path).
        model_id: Optional model override. Falls back to AGENT_MODEL_ID env var,
            then to claude-sonnet-4-20250514.
    """
    if llm_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("[AGENT] ANTHROPIC_API_KEY not configured")
            return {"error": "ANTHROPIC_API_KEY not configured.", "answer": None}
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = None

    _model = model_id or os.getenv("AGENT_MODEL_ID", "claude-sonnet-4-20250514")

    if cache_manager is None:
        from cache_manager import get_cache_manager
        cache_manager = get_cache_manager()

    # Build the user message -- include AOI context if provided
    drawn_aois = []
    user_content = question
    has_aoi = aoi is not None
    if aoi:
        aoi_type = (aoi.get("type") or "").lower()
        if aoi_type == "featurecollection":
            features = aoi.get("features", [])
            for i, feat in enumerate(features):
                label = (feat.get("properties") or {}).get("label", f"Area {i + 1}")
                drawn_aois.append({"label": label, "geometry": feat.get("geometry", feat)})
            user_content += (
                f"\n\n[The user has drawn {len(drawn_aois)} areas on the map. "
                f"To compare them, call analyze_area once for each area with aoi={{}}. "
                f"The system will inject each polygon in sequence. "
                f"Area labels: {', '.join(d['label'] for d in drawn_aois)}]"
            )
        else:
            aoi_name = ""
            if isinstance(aoi, dict):
                aoi_name = (aoi.get("properties") or {}).get("name", "")
            user_content += (
                f"\n\n[The user has selected an area on the map"
                f"{' (' + aoi_name + ')' if aoi_name else ''}. "
                f"Call analyze_area with aoi={{}} -- the system injects the geometry automatically.]"
            )

    logger.info("[AGENT] === New query === Question: %s | Has AOI: %s | Session: %s",
                question[:200], has_aoi, session_id or "none")
    t_start = _time_mod.time()

    total_input_tokens = 0
    total_output_tokens = 0

    from agent.event_logger import generate_query_id
    query_id = generate_query_id()

    # Security: sanitise user input before sending to LLM
    user_content = sanitize_input(user_content)

    # Detect language for fallback messages
    user_lang = detect_language(question)

    # Restore conversation history from session store
    history = session_store.get_messages(session_id)
    messages = history + [{"role": "user", "content": user_content}]
    tools_used = []
    actions = []
    chart_urls = []
    last_analyzed_layer_ref = [None]
    province_aoi = None
    province_geometries = []
    analysis_results = []
    current_province_name = None
    drawn_aoi_idx = 0

    for _round in range(MAX_TOOL_ROUNDS):
        logger.info("[AGENT] Round %d/%d -- calling LLM", _round + 1, MAX_TOOL_ROUNDS)
        t_llm = _time_mod.time()

        if llm_client is not None:
            response = llm_client.create_message(
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS,
                max_tokens=2048,
            )
        else:
            response = client.messages.create(
                model=_model,
                max_tokens=2048,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=TOOLS,
                messages=messages,
            )

        llm_ms = int((_time_mod.time() - t_llm) * 1000)
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
        logger.info(
            "[AGENT] Round %d -- LLM responded in %dms | stop_reason: %s | usage: in=%d out=%d",
            _round + 1, llm_ms, response.stop_reason,
            response.usage.input_tokens, response.usage.output_tokens,
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            assistant_content = response.content

            # --- Separate tools into state-setting (sequential) and independent (parallelizable) ---
            sequential_blocks = []
            parallel_blocks = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if block.name in ("lookup_province", "lookup_municipality"):
                    sequential_blocks.append(block)
                else:
                    parallel_blocks.append(block)

            # --- Phase 1: Execute state-setting tools sequentially ---
            round_lookups = []

            for block in sequential_blocks:
                tool_input = block.input

                if block.name == "lookup_province":
                    from agent.provinces import lookup_province as _lp
                    prov = _lp(tool_input.get("name", ""))
                    if prov:
                        province_aoi = prov["geometry"]
                        current_province_name = prov["name"]
                        round_lookups.append({"name": prov["name"], "aoi": prov["geometry"]})
                        province_geometries.append({
                            "name": prov["name"],
                            "geometry": prov["geometry"],
                            "bounds": prov["bounds"],
                        })
                        actions.append({
                            "type": "show_province_boundary",
                            "geojson": {
                                "type": "Feature",
                                "geometry": prov["geometry"],
                                "properties": {"name": prov["name"]},
                            },
                        })
                    else:
                        # Fallback: Portuguese district lookup (no full geometry,
                        # but name + bounds suffice for JSON-backed indicators).
                        from agent.tools.executors import _lookup_portugal_district
                        pt = _lookup_portugal_district(tool_input.get("name", ""))
                        if pt and pt.get("found"):
                            bounds = pt["bounds"]
                            # Synthesize a bbox polygon so analyze_area has a geometry
                            bbox_geom = {
                                "type": "Polygon",
                                "coordinates": [[
                                    [bounds[0], bounds[1]],
                                    [bounds[2], bounds[1]],
                                    [bounds[2], bounds[3]],
                                    [bounds[0], bounds[3]],
                                    [bounds[0], bounds[1]],
                                ]],
                            }
                            province_aoi = {"type": "Feature", "geometry": bbox_geom, "properties": {"name": pt["name"], "district": pt["name"]}}
                            current_province_name = pt["name"]
                            round_lookups.append({"name": pt["name"], "aoi": province_aoi})
                            province_geometries.append({
                                "name": pt["name"],
                                "geometry": bbox_geom,
                                "bounds": bounds,
                            })
                            actions.append({
                                "type": "fly_to_bounds",
                                "bounds": bounds,
                            })

                if block.name == "lookup_municipality":
                    from admin_manager import get_admin_manager as _get_am
                    from agent.tools.executors import exec_lookup_municipality
                    mgr = _get_am()
                    muni_name = tool_input.get("name", "")
                    muni_prov = tool_input.get("province", "")
                    muni_res = exec_lookup_municipality(muni_name, muni_prov)
                    if muni_res.get("found") and muni_res.get("code"):
                        muni_feat = mgr.get_geometry("municipality", muni_res["code"])
                        if muni_feat and muni_feat.get("geometry"):
                            province_aoi = muni_feat["geometry"]
                            current_province_name = muni_res.get("name", "")
                            round_lookups.append({"name": muni_res.get("name", ""), "aoi": muni_feat["geometry"]})
                            province_geometries.append({
                                "name": muni_res.get("name", ""),
                                "geometry": muni_feat["geometry"],
                                "bounds": muni_res.get("bounds", [-180, -90, 180, 90]),
                            })
                            actions.append({
                                "type": "show_province_boundary",
                                "geojson": {
                                    "type": "Feature",
                                    "geometry": muni_feat["geometry"],
                                    "properties": {"name": muni_res.get("name", "")},
                                },
                            })

                t_tool = _time_mod.time()
                result_str = execute_tool(block.name, tool_input, cache_manager, user)
                tool_ms = int((_time_mod.time() - t_tool) * 1000)
                logger.info("[AGENT] Tool %s executed in %dms", block.name, tool_ms)

                _process_tool_result(
                    block, tool_input, result_str,
                    analysis_results, actions, tools_used,
                    current_province_name, last_analyzed_layer_ref,
                    chart_urls,
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

            # --- Phase 2: Prepare and execute independent tools (potentially in parallel) ---
            parallel_inputs = []
            analyze_idx = 0
            for block in parallel_blocks:
                tool_input = dict(block.input)
                if block.name == "analyze_area":
                    if len(round_lookups) > 1 and analyze_idx < len(round_lookups):
                        tool_input["aoi"] = round_lookups[analyze_idx]["aoi"]
                        tool_input["_province_name"] = round_lookups[analyze_idx]["name"]
                        analyze_idx += 1
                    elif province_aoi:
                        tool_input["aoi"] = province_aoi
                        tool_input["_province_name"] = current_province_name
                    elif drawn_aois and drawn_aoi_idx < len(drawn_aois):
                        tool_input["aoi"] = drawn_aois[drawn_aoi_idx]["geometry"]
                        tool_input["_province_name"] = drawn_aois[drawn_aoi_idx]["label"]
                        drawn_aoi_idx += 1
                    elif aoi:
                        tool_input["aoi"] = aoi
                        tool_input["_province_name"] = current_province_name
                parallel_inputs.append((block, tool_input))

            if parallel_inputs and PARALLEL_TOOLS_ENABLED and len(parallel_inputs) > 1:
                t_parallel = _time_mod.time()
                logger.info("[AGENT] Executing %d tools in parallel", len(parallel_inputs))
                ordered_results = [None] * len(parallel_inputs)

                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    future_to_idx = {}
                    for idx, (block, tool_input) in enumerate(parallel_inputs):
                        exec_input = {k: v for k, v in tool_input.items() if not k.startswith("_")}
                        future = executor.submit(execute_tool, block.name, exec_input, cache_manager, user)
                        future_to_idx[future] = idx

                    for future in concurrent.futures.as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            ordered_results[idx] = future.result()
                        except Exception as exc:
                            logger.exception("[AGENT] Parallel tool execution error")
                            ordered_results[idx] = json.dumps({"error": str(exc)})

                parallel_ms = int((_time_mod.time() - t_parallel) * 1000)
                logger.info("[AGENT] Parallel execution of %d tools completed in %dms", len(parallel_inputs), parallel_ms)

                for idx, (block, tool_input) in enumerate(parallel_inputs):
                    result_str = ordered_results[idx]
                    _process_tool_result(
                        block, tool_input, result_str,
                        analysis_results, actions, tools_used,
                        current_province_name, last_analyzed_layer_ref,
                        chart_urls,
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })
            else:
                for block, tool_input in parallel_inputs:
                    t_tool = _time_mod.time()
                    exec_input = {k: v for k, v in tool_input.items() if not k.startswith("_")}
                    result_str = execute_tool(block.name, exec_input, cache_manager, user)
                    tool_ms = int((_time_mod.time() - t_tool) * 1000)
                    logger.info("[AGENT] Tool %s executed in %dms", block.name, tool_ms)

                    _process_tool_result(
                        block, tool_input, result_str,
                        analysis_results, actions, tools_used,
                        current_province_name, last_analyzed_layer_ref,
                        chart_urls,
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "max_tokens":
            # Model ran out of output tokens mid-generation -- continue in next round
            logger.warning("[AGENT] Round %d hit max_tokens -- continuing", _round + 1)
            partial_content = response.content
            messages.append({"role": "assistant", "content": partial_content})
            messages.append({"role": "user", "content": "Continue -- you were cut off mid-response."})
            continue

        else:
            # Final text response (end_turn)
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            answer = sanitize_output("\n".join(text_parts))

            # Safety net: if analysis ran but LLM returned empty text, generate a summary
            if not answer.strip() and analysis_results:
                logger.warning("[AGENT] Empty answer with %d analysis results -- generating fallback", len(analysis_results))
                parts = []
                for ar in analysis_results:
                    label = ar["label"]
                    res = ar["result"]
                    if res.get("type") == "categorical" and "breakdown" in res:
                        summary = ", ".join(f"{e['label']}: {e['percentage']:.1f}%" for e in res["breakdown"][:4])
                        parts.append(f"**{label}**: {summary}")
                    elif res.get("type") == "continuous" and "statistics" in res:
                        stats = res["statistics"]
                        mean_val = stats.get("mean", 0)
                        unit = stats.get("unit", "")
                        parts.append(f"**{label}**: mean {mean_val:.1f}{unit}")
                if parts:
                    prefix = "Estos son los resultados:" if user_lang == "es" else "Here are the results:"
                    answer = f"{prefix}\n\n" + "\n\n".join(parts)

            # Auto-toggle the last analyzed layer
            last_analyzed_layer = last_analyzed_layer_ref[0]
            if last_analyzed_layer:
                actions.append({
                    "type": "toggle_layer",
                    "indicator": last_analyzed_layer["indicator"],
                    "year": last_analyzed_layer["year"],
                    "season": last_analyzed_layer["season"],
                    "visible": True,
                    "display_name": last_analyzed_layer["indicator"].replace("_", " ").title(),
                    "bounds": None,
                })

            # Auto-toggle contextual layers when CO2 was analyzed
            co2_analyzed = any(
                r.get("tool_input", {}).get("indicator") == "co2_spain_legislation"
                for r in analysis_results if "error" not in r.get("result", {})
            )
            if co2_analyzed:
                actions.append({
                    "type": "toggle_layer",
                    "indicator": "burnt_areas",
                    "year": "2024", "season": "annual",
                    "visible": True,
                    "display_name": "Burnt Areas (EFFIS) 2000-2024",
                    "bounds": None,
                })
                actions.append({
                    "type": "toggle_layer",
                    "indicator": "mfe",
                    "year": "2024", "season": "annual",
                    "visible": True,
                    "display_name": "Spanish Forest Map (MFE)",
                    "bounds": None,
                })

            # Auto-generate report for all analyses
            if analysis_results:
                report_action = build_report(analysis_results, lang=user_lang)
                if report_action:
                    actions.append(report_action)

            # Populate province_geometries from request-level AOI if no lookups occurred
            if not province_geometries and analysis_results and aoi:
                if drawn_aois:
                    for da in drawn_aois:
                        geom = da["geometry"]
                        bounds = _bounds_from_geometry(geom)
                        province_geometries.append({"name": da["label"], "geometry": geom, "bounds": bounds})
                        actions.append({
                            "type": "show_province_boundary",
                            "geojson": {"type": "Feature", "geometry": geom, "properties": {"name": da["label"]}},
                        })
                else:
                    geom = aoi
                    name = "Selected area"
                    if aoi.get("type") == "Feature":
                        geom = aoi.get("geometry", aoi)
                        name = (aoi.get("properties") or {}).get("name", name)
                    bounds = _bounds_from_geometry(geom)
                    province_geometries.append({"name": name, "geometry": geom, "bounds": bounds})
                    actions.append({
                        "type": "show_province_boundary",
                        "geojson": {"type": "Feature", "geometry": geom, "properties": {"name": name}},
                    })

            # Build combined crop + fly_to action from all provinces
            if province_geometries:
                all_w = min(p["bounds"][0] for p in province_geometries)
                all_s = min(p["bounds"][1] for p in province_geometries)
                all_e = max(p["bounds"][2] for p in province_geometries)
                all_n = max(p["bounds"][3] for p in province_geometries)
                actions.append({
                    "type": "fly_to_bounds",
                    "bounds": [[all_w, all_s], [all_e, all_n]],
                })
                actions.append({
                    "type": "crop_to_provinces",
                    "geojson": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": p["geometry"],
                                "properties": {"name": p["name"]},
                            }
                            for p in province_geometries
                        ],
                    },
                })

            # Save conversation to session store
            session_store.save_messages(session_id, messages + [
                {"role": "assistant", "content": answer},
            ])

            usage = {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "rounds": _round + 1,
            }
            total_ms = int((_time_mod.time() - t_start) * 1000)
            logger.info(
                "[AGENT] === Query complete === Rounds: %d | Tools: %s | Provinces: %s | "
                "Tokens: in=%d out=%d total=%d | Total: %dms",
                _round + 1,
                [t["tool"] for t in tools_used],
                [p["name"] for p in province_geometries],
                total_input_tokens, total_output_tokens,
                total_input_tokens + total_output_tokens,
                total_ms,
            )

            try:
                from rate_limiter import record_token_usage
                record_token_usage(total_input_tokens, total_output_tokens)
            except Exception:
                pass

            try:
                from agent.event_logger import log_query_event
                log_query_event(
                    query_id=query_id,
                    session_id=session_id,
                    question=question,
                    answer=answer,
                    tools_used=tools_used,
                    actions=actions,
                    usage=usage,
                    duration_ms=total_ms,
                    prompt_version=os.getenv("AGENT_PROMPT_VERSION", "v3"),
                    provinces=[p["name"] for p in province_geometries],
                    indicators=list({t["input"].get("indicator", "") for t in tools_used if "input" in t} - {""}),
                    success=True,
                )
            except Exception:
                logger.warning("[AGENT] Event logging failed", exc_info=True)

            return {
                "answer": answer,
                "full_answer": answer,
                "tools_used": tools_used,
                "actions": actions,
                "usage": usage,
                "query_id": query_id,
                "chart_urls": chart_urls,
                "conversation_trace": _serialize_messages(messages),
                "analysis_results": analysis_results,
            }

    # --- Exhausted rounds --- build a useful fallback response (language-aware) ---
    if user_lang == "es":
        fallback_parts = ["No pude completar el analisis dentro de los pasos permitidos."]
    else:
        fallback_parts = ["I wasn't able to fully complete the analysis within the allowed steps."]
    if analysis_results:
        n = len(analysis_results)
        if user_lang == "es":
            fallback_parts.append(f"Esto es lo que encontre ({n} area(s) analizada(s)):")
        else:
            fallback_parts.append(f"Here's what I found so far ({n} area(s) analyzed):")
        for ar in analysis_results:
            label = ar["label"]
            res = ar["result"]
            if res.get("type") == "categorical" and "breakdown" in res:
                summary = ", ".join(f"{e['label']}: {e['percentage']}%" for e in res["breakdown"][:4])
                fallback_parts.append(f"- **{label}**: {summary}")
            elif "error" not in res:
                stats = res.get("statistics", {})
                mean_val = stats.get("mean", 0)
                unit = stats.get("unit", "")
                fallback_parts.append(f"- **{label}**: mean {mean_val:.1f}{unit}")
    if province_geometries:
        names = [p["name"] for p in province_geometries]
        if user_lang == "es":
            fallback_parts.append(f"Provincias localizadas: {', '.join(names)}.")
        else:
            fallback_parts.append(f"Provinces located: {', '.join(names)}.")
    if user_lang == "es":
        fallback_parts.append("Intenta hacer una pregunta mas especifica o dividirla en pasos mas pequenos.")
    else:
        fallback_parts.append("Try asking a more specific question or break it into smaller steps.")
    fallback_answer = sanitize_output("\n".join(fallback_parts))

    # Still generate report from partial results
    if analysis_results:
        report_action = build_report(analysis_results, lang=user_lang)
        if report_action:
            actions.append(report_action)
    if province_geometries:
        all_w = min(p["bounds"][0] for p in province_geometries)
        all_s = min(p["bounds"][1] for p in province_geometries)
        all_e = max(p["bounds"][2] for p in province_geometries)
        all_n = max(p["bounds"][3] for p in province_geometries)
        actions.append({"type": "fly_to_bounds", "bounds": [[all_w, all_s], [all_e, all_n]]})

    usage = {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "rounds": MAX_TOOL_ROUNDS,
    }
    total_ms = int((_time_mod.time() - t_start) * 1000)
    logger.warning(
        "[AGENT] === Query exhausted rounds === Tools: %s | Tokens: in=%d out=%d | Total: %dms",
        tools_used, total_input_tokens, total_output_tokens, total_ms,
    )

    try:
        from rate_limiter import record_token_usage
        record_token_usage(total_input_tokens, total_output_tokens)
    except Exception:
        pass

    try:
        from agent.event_logger import log_query_event
        log_query_event(
            query_id=query_id,
            session_id=session_id,
            question=question,
            answer=fallback_answer,
            tools_used=tools_used,
            actions=actions,
            usage=usage,
            duration_ms=total_ms,
            prompt_version=os.getenv("AGENT_PROMPT_VERSION", "v3"),
            provinces=[p["name"] for p in province_geometries],
            indicators=list({t["input"].get("indicator", "") for t in tools_used if "input" in t} - {""}),
            success=False,
        )
    except Exception:
        logger.warning("[AGENT] Event logging failed", exc_info=True)

    return {
        "answer": fallback_answer,
        "full_answer": fallback_answer,
        "tools_used": tools_used,
        "actions": actions,
        "usage": usage,
        "query_id": query_id,
        "chart_urls": chart_urls,
        "conversation_trace": _serialize_messages(messages),
        "analysis_results": analysis_results,
    }
