"""Tool executor functions — direct Python calls (no HTTP round-trips).

Each exec_* function implements a single tool.
All functions return a dict (serialized to JSON by the dispatcher).
"""

import concurrent.futures
import io
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Display scale factors for continuous indicators (byte → human-readable)
DISPLAY_SCALE_FACTORS: Dict[str, float] = {
    "rf_gully_probability": 1.0 / 2.55,
}

INDICATOR_UNITS: Dict[str, str] = {
    "rf_gully_probability": "%",
}

# Canonical year/season for each indicator — normalize agent-supplied values to these
# so that wrong guesses (e.g. year="2024" for rf_gully_probability) still resolve correctly.
INDICATOR_VERSIONS: Dict[str, Dict[str, str]] = {
    "rf_gully_probability": {"year": "2022", "season": "annual"},
    "co2_spain_legislation": {"year": "2026", "season": "annual"},
    "bigearthnet_lulc": {"year": "2018", "season": "annual"},
}

# Indicators served from pre-computed JSON instead of COG rasters.
# Maps indicator name to the JSON file path (relative to api/data/).
JSON_INDICATORS: Dict[str, str] = {
    "bigearthnet_lulc": "bigearthnet_portugal_stats.json",
}

# WMS layers not tracked by cache_manager — maintained here as fallback
WMS_LAYERS = {
    "ines_erosion_potencial": {
        "year": "static", "season": "static",
        "display_name": "Potential Erosion (sheet and rill)",
        "bounds": [-18.21, 27.63, 4.89, 43.97],
    },
    "ines_movimientos_masa": {
        "year": "static", "season": "static",
        "display_name": "Mass Movements - Potential",
        "bounds": [-18.21, 27.63, 4.89, 43.97],
    },
    "ines_erosion_eolica": {
        "year": "static", "season": "static",
        "display_name": "Wind Erosion - Risk",
        "bounds": [-18.21, 27.63, 4.89, 43.97],
    },
}

# Vector/PMTiles display-only layers
VECTOR_DISPLAY_LAYERS = {
    "mfe": {
        "year": "2024", "season": "annual",
        "display_name": "Spanish Forest Map (MFE)",
        "bounds": [-18.21, 27.63, 4.89, 43.97],
    },
    "burnt_areas": {
        "year": "2024", "season": "annual",
        "display_name": "Burnt Areas (EFFIS) 2000-2024",
        "bounds": [-25, 27, 45, 72],
    },
    "lucas_gully_channels": {
        "year": "2022", "season": "annual",
        "display_name": "LUCAS Points with Detected Gullies",
        "bounds": [-25, 34, 45, 72],
    },
    "lucas_gully_locations": {
        "year": "2022", "season": "annual",
        "display_name": "Actual Gully Channel Locations",
        "bounds": [-25, 34, 45, 72],
    },
    "lucas_survey_points": {
        "year": "2022", "season": "annual",
        "display_name": "All LUCAS 2022 Survey Points",
        "bounds": [-25, 34, 45, 72],
    },
    "lucas_crosscheck_random": {
        "year": "2022", "season": "annual",
        "display_name": "Random Cross-Check Validation (LUCAS)",
        "bounds": [-25, 34, 45, 72],
    },
    "lucas_crosscheck_omission": {
        "year": "2022", "season": "annual",
        "display_name": "Omission Error Cross-Check (LUCAS)",
        "bounds": [-25, 34, 45, 72],
    },
}


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------


def exec_list_layers(cache_manager, user: Optional[Dict] = None) -> Dict[str, Any]:
    from services.tile_tenant import filter_layers_by_access

    all_layers = cache_manager.list_available_indicators()
    result = []
    for layer in all_layers:
        info = layer if isinstance(layer, dict) else {"indicator": layer}
        result.append({
            "indicator": info.get("indicator", str(layer)),
            "year": info.get("year", ""),
            "season": info.get("season", ""),
            "description": (info.get("metadata") or {}).get("description_en", ""),
            "access_tier": info.get("access_tier", "guest"),
        })
    return {"layers": result}


def exec_get_legend(indicator: str) -> Dict[str, Any]:
    from symbology.registry import get_legend_items

    items = get_legend_items(indicator)
    return {"indicator": indicator, "items": items}


def _exec_analyze_area_json(
    indicator: str, year: str, season: str, aoi: Dict[str, Any],
) -> Dict[str, Any]:
    """Serve pre-computed statistics from a JSON file instead of reading a COG raster.

    Used for indicators backed by static datasets (e.g. bigearthnet_lulc) where
    the data is pre-aggregated per administrative district.
    """
    json_file = JSON_INDICATORS.get(indicator)
    if not json_file:
        return {"error": f"No JSON source for indicator '{indicator}'."}

    data_path = Path(__file__).parent.parent.parent / "data" / json_file
    if not data_path.exists():
        return {"error": f"Data file not found: {json_file}. Run scripts/prepare_bigearthnet_layer.py first."}

    with open(data_path) as f:
        all_stats = json.load(f)

    # Match AOI to a district by name.
    # The AOI may come from _lookup_portugal_district (flat dict with "name" key)
    # or from a GeoJSON feature with properties.
    district_name = None

    if isinstance(aoi, dict):
        # Direct name from _lookup_portugal_district result
        district_name = aoi.get("name")

        # Check GeoJSON properties
        if not district_name:
            props = aoi.get("properties", {})
            if isinstance(props, dict):
                district_name = props.get("district") or props.get("name")

        # Fallback: injected by runner or calling context
        if not district_name:
            district_name = aoi.get("_district_name")

    if not district_name:
        # Try fuzzy match using available district names
        available = list(all_stats.keys())
        return {
            "error": f"Could not determine district name from AOI. "
            f"bigearthnet_lulc covers Portugal districts: {', '.join(available)}",
        }

    # Fuzzy match district name
    from difflib import get_close_matches
    available = list(all_stats.keys())
    matches = get_close_matches(district_name, available, n=1, cutoff=0.6)
    if not matches:
        return {
            "error": f"District '{district_name}' not found in bigearthnet_lulc data. "
            f"Available: {', '.join(available)}",
        }

    matched_name = matches[0]
    stats = all_stats[matched_name]

    return {
        "type": stats["type"],
        "total_patches": stats["total_patches"],
        "source": stats["source"],
        "district": matched_name,
        "year": stats["year"],
        "breakdown": stats["breakdown"],
    }


def exec_analyze_area(
    indicator: str, year: str, season: str, aoi: Dict[str, Any],
    cache_manager, user: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Mask the raster with the AOI and compute statistics."""
    import rasterio
    from rasterio.mask import mask as rio_mask

    from symbology.registry import get_symbology

    # Normalize year/season to the known canonical values for each indicator.
    # Prevents failures when the agent guesses a wrong year (e.g. "2024" for rf_gully_probability).
    if indicator in INDICATOR_VERSIONS:
        canonical = INDICATOR_VERSIONS[indicator]
        if str(year) != canonical["year"] or season != canonical["season"]:
            logger.warning(
                "[AGENT] Normalizing %s params: %s/%s → %s/%s",
                indicator, year, season, canonical["year"], canonical["season"],
            )
            year = canonical["year"]
            season = canonical["season"]

    # JSON-backed indicators: serve from pre-computed stats instead of reading COG rasters.
    if indicator in JSON_INDICATORS:
        return _exec_analyze_area_json(indicator, year, season, aoi)

    layer_info = cache_manager.get_layer_info(indicator, str(year), season)
    if not layer_info:
        return {"error": f"Layer {indicator}/{year}/{season} not found."}

    tile_url = cache_manager.get_tile_url(indicator, year, season)
    if not tile_url:
        return {"error": "Could not resolve layer source."}

    # Open-source build: layers always resolve to local files via the
    # vendored cache_manager. No gs:// URLs are produced at this point.

    # Build shapes list from AOI geometry
    geom_type = (aoi.get("type") or "").lower()
    if geom_type in ("polygon", "multipolygon"):
        shapes = [aoi]
    elif geom_type == "feature":
        shapes = [aoi.get("geometry", aoi)]
    elif geom_type == "featurecollection":
        shapes = [f["geometry"] for f in aoi.get("features", []) if f.get("geometry")]
    else:
        return {"error": f"Unsupported AOI geometry type: {aoi.get('type')}"}

    needs_env = isinstance(tile_url, str) and tile_url.startswith(("http", "/vsigs", "/vsicurl"))

    try:
        from rasterio.warp import transform_geom

        gdal_env = {
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "VSI_CACHE": "TRUE",
            "GDAL_HTTP_TIMEOUT": "60",
            "GDAL_HTTP_MAX_RETRY": "2",
            "GDAL_HTTP_LOW_SPEED_TIME": "30",
            "GDAL_HTTP_LOW_SPEED_LIMIT": "1",
        }

        def _read_raster():
            ctx = rasterio.Env(**gdal_env) if needs_env else __import__("contextlib").nullcontext()
            with ctx:
                with rasterio.open(tile_url) as src:
                    _shapes = shapes
                    raster_crs = getattr(src, "crs", None)
                    if raster_crs:
                        crs_obj = rasterio.crs.CRS.from_user_input(raster_crs)
                        if crs_obj and crs_obj.to_epsg() != 4326:
                            _shapes = [
                                transform_geom("EPSG:4326", crs_obj, geom, precision=6)
                                for geom in shapes
                            ]
                    return rio_mask(src, _shapes, crop=True, nodata=src.nodata)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            data, _ = executor.submit(_read_raster).result(timeout=120)
    except concurrent.futures.TimeoutError:
        return {"error": "Raster read timed out — province area may be too large."}
    except ValueError as exc:
        if "Input shapes do not overlap" in str(exc):
            return {"error": "The selected area does not overlap with this layer."}
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Failed to read raster: {exc}"}

    band = data[0].flatten()

    # Remove nodata
    symbology = get_symbology(indicator)
    nodata_vals = set()
    if symbology and symbology.metadata:
        nd = symbology.metadata.get("nodata")
        if isinstance(nd, list):
            nodata_vals.update(nd)
        elif nd is not None:
            nodata_vals.add(nd)
    valid = np.isfinite(band) if np.issubdtype(band.dtype, np.floating) else np.ones(band.shape, dtype=bool)
    for ndv in nodata_vals:
        valid &= band != ndv

    band = band[valid]
    if band.size == 0:
        return {"error": "No valid data pixels in the selected area."}

    total = int(band.size)

    if symbology and symbology.type == "categorical":
        unique, counts = np.unique(band, return_counts=True)
        legend = {e.value: e.label for e in (symbology.entries or [])}
        breakdown = []
        for v, c in zip(unique.tolist(), counts.tolist()):
            int_v = int(v) if float(v).is_integer() else v
            breakdown.append({
                "value": int_v,
                "label": legend.get(int_v, f"Class {int_v}"),
                "pixel_count": c,
                "percentage": round(c / total * 100, 1),
            })
        return {"type": "categorical", "total_pixels": total, "breakdown": breakdown}
    else:
        scale = DISPLAY_SCALE_FACTORS.get(indicator, 1.0)
        unit = INDICATOR_UNITS.get(indicator, "")
        return {
            "type": "continuous",
            "total_pixels": total,
            "statistics": {
                "min": round(float(np.min(band)) * scale, 1),
                "max": round(float(np.max(band)) * scale, 1),
                "mean": round(float(np.mean(band)) * scale, 1),
                "median": round(float(np.median(band)) * scale, 1),
                "std": round(float(np.std(band)) * scale, 1),
                "unit": unit,
            },
        }


def _lookup_portugal_district(name: str) -> Optional[Dict[str, Any]]:
    """Look up a Portuguese district by name. Returns match or None."""
    from difflib import get_close_matches

    districts_path = Path(__file__).parent.parent.parent / "data" / "portugal_districts.json"
    if not districts_path.exists():
        return None

    with open(districts_path) as f:
        data = json.load(f)

    districts = data.get("districts", {})
    # Normalize for matching
    norm_map = {k.lower(): k for k in districts}

    # Exact match (case-insensitive)
    if name.lower() in norm_map:
        key = norm_map[name.lower()]
        d = districts[key]
        return {
            "name": key,
            "code": d["code"],
            "bounds": d["bounds"],
            "country": "Portugal",
            "found": True,
        }

    # Fuzzy match
    matches = get_close_matches(name.lower(), norm_map.keys(), n=1, cutoff=0.6)
    if matches:
        key = norm_map[matches[0]]
        d = districts[key]
        return {
            "name": key,
            "code": d["code"],
            "bounds": d["bounds"],
            "country": "Portugal",
            "found": True,
        }

    return None


def exec_lookup_province(name: str) -> Dict[str, Any]:
    """Look up a Spanish province or Portuguese district by name.

    Tries Spanish provinces first (primary coverage), then falls back to
    Portuguese districts for BigEarthNet LULC queries.
    """
    from agent.provinces import lookup_province, list_province_names

    result = lookup_province(name)
    if result is not None:
        return {
            "name": result["name"],
            "code": result["code"],
            "bounds": result["bounds"],
            "found": True,
        }

    # Fall back to Portuguese districts
    pt_result = _lookup_portugal_district(name)
    if pt_result is not None:
        return pt_result

    available = list_province_names()[:10]
    return {"error": f"Province '{name}' not found. Some valid names: {', '.join(available)}"}


def exec_lookup_municipality(name: str, province_hint: str = "") -> Dict[str, Any]:
    """Look up a Spanish municipality by name. Returns summary (no full geometry).
    Reuses _normalize and _compute_bounds from provinces.py to avoid duplication."""
    from difflib import get_close_matches
    from admin_manager import get_admin_manager
    from agent.provinces import _normalize, _compute_bounds

    mgr = get_admin_manager()
    index = mgr.get_index()
    munis = [e for e in index if e["type"] == "municipality"]

    norm_name = _normalize(name)

    # If province hint given, filter candidates
    if province_hint:
        norm_prov = _normalize(province_hint)
        filtered = [m for m in munis if norm_prov in _normalize(m.get("province_name", ""))]
        if filtered:
            munis = filtered

    def _build_result(m):
        feature = mgr.get_geometry("municipality", m["code"])
        bounds = _compute_bounds(feature["geometry"]) if feature and feature.get("geometry") else None
        return {
            "name": m["name"], "code": m["code"],
            "province_name": m.get("province_name", ""),
            "ccaa_name": m.get("ccaa_name", ""),
            "bounds": bounds, "found": True,
        }

    # Exact match
    for m in munis:
        if _normalize(m["name"]) == norm_name:
            return _build_result(m)

    # Fuzzy match
    name_to_entry = {_normalize(m["name"]): m for m in munis}
    matches = get_close_matches(norm_name, name_to_entry.keys(), n=3, cutoff=0.7)
    if matches:
        result = _build_result(name_to_entry[matches[0]])
        if len(matches) > 1:
            result["candidates"] = [
                f"{name_to_entry[m]['name']} ({name_to_entry[m].get('province_name', '')})"
                for m in matches
            ]
        return result

    return {"error": f"Municipality '{name}' not found.", "found": False}


def exec_get_layer_bounds(
    indicator: str, year: str, season: str, cache_manager,
) -> Dict[str, Any]:
    tile_url = cache_manager.get_tile_url(indicator, year, season)
    if not tile_url:
        return {"error": "Layer not found."}

    try:
        from rio_tiler.io import COGReader
        import rasterio

        GDAL_CONFIG = {
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "VSI_CACHE": "TRUE",
        }
        needs_env = isinstance(tile_url, str) and tile_url.startswith(("http", "/vsigs"))
        ctx = rasterio.Env(**GDAL_CONFIG) if needs_env else __import__("contextlib").nullcontext()
        with ctx:
            with COGReader(tile_url) as cog:
                bounds = cog.geographic_bounds
                return {"bounds": list(bounds), "crs": "EPSG:4326"}
    except Exception as exc:
        return {"error": f"Could not read bounds: {exc}"}


# ---------------------------------------------------------------------------
# PoC tools — agent-agnostic, self-contained where possible
# ---------------------------------------------------------------------------


def _get_gcs_bucket() -> str:
    """Resolve GCS bucket name: BUCKET (Cloud Run) → CB_BUCKET (Cloud Build) → defaults.yaml."""
    import yaml

    if bucket := os.environ.get("BUCKET") or os.environ.get("CB_BUCKET"):
        return bucket
    defaults_path = Path(__file__).parents[3] / "cloudbuild-builds" / "config" / "defaults.yaml"
    with open(defaults_path) as f:
        return yaml.safe_load(f)["bucket"]


def _comparison_note(
    name_a: str, stats_a: Dict, name_b: str, stats_b: Dict, indicator: str,
) -> str:
    """One-line human-readable comparison summary."""
    try:
        if stats_a.get("type") == "categorical":
            def _eligible_pct(stats):
                for item in stats.get("breakdown", []):
                    if item.get("value") == 2:
                        return item.get("percentage", 0.0)
                return 0.0
            pct_a, pct_b = _eligible_pct(stats_a), _eligible_pct(stats_b)
            winner = name_a if pct_a >= pct_b else name_b
            hi, lo = max(pct_a, pct_b), min(pct_a, pct_b)
            return f"{winner} has higher CO2 eligibility ({hi:.1f}% vs {lo:.1f}%)."
        if stats_a.get("type") == "continuous":
            mean_a = stats_a.get("statistics", {}).get("mean", 0.0)
            mean_b = stats_b.get("statistics", {}).get("mean", 0.0)
            unit = stats_a.get("statistics", {}).get("unit", "")
            if "erosion" in indicator or "gully" in indicator:
                lower = name_a if mean_a <= mean_b else name_b
                return f"{lower} has lower erosion risk ({min(mean_a, mean_b):.1f}{unit} vs {max(mean_a, mean_b):.1f}{unit})."
            winner = name_a if mean_a >= mean_b else name_b
            return f"{winner} has a higher mean ({max(mean_a, mean_b):.1f}{unit} vs {min(mean_a, mean_b):.1f}{unit})."
    except Exception:
        pass
    return ""


def exec_compare_areas(
    area_a: str, area_b: str,
    indicator: str, year: str, season: str,
    cache_manager, user: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Compare two provinces side-by-side on a single indicator (parallel reads)."""
    from concurrent.futures import ThreadPoolExecutor

    from agent.provinces import lookup_province

    def _analyze(name: str):
        prov = lookup_province(name)
        if prov is None:
            return name, {"error": f"Province '{name}' not found."}
        return prov["name"], exec_analyze_area(
            indicator, year, season, prov["geometry"], cache_manager, user,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(_analyze, area_a)
        future_b = executor.submit(_analyze, area_b)
        name_a, stats_a = future_a.result()
        name_b, stats_b = future_b.result()

    return {
        "area_a": {"name": name_a, "stats": stats_a},
        "area_b": {"name": name_b, "stats": stats_b},
        "comparison_note": _comparison_note(name_a, stats_a, name_b, stats_b, indicator),
    }


def exec_find_top_n(
    metric: str, n: int = 10, order: str = "desc",
    filter_provinces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Find top/bottom N provinces by metric from pre-computed rankings (instant, no raster reads)."""
    METRIC_MAP = {
        "co2_eligible_pct":    ("co2",     "eligible_pct"),
        "co2_conditional_pct": ("co2",     "conditional_pct"),
        "co2_not_eligible_pct":("co2",     "not_eligible_pct"),
        "erosion_mean_pct":    ("erosion", "mean_pct"),
        "erosion_max_pct":     ("erosion", "max_pct"),
    }
    if metric not in METRIC_MAP:
        return {"error": f"Unknown metric '{metric}'. Valid: {list(METRIC_MAP.keys())}"}

    rankings_path = Path(__file__).parent.parent / "province_rankings.json"
    with open(rankings_path) as f:
        data = json.load(f)

    section, field = METRIC_MAP[metric]
    rows = []
    for prov in data.get("provinces", {}).values():
        val = (prov.get(section) or {}).get(field)
        if val is None:
            continue
        if filter_provinces and prov["name"] not in filter_provinces:
            continue
        rows.append({"province": prov["name"], "value": val})

    rows.sort(key=lambda x: x["value"], reverse=(order == "desc"))
    rows = rows[:n]
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    return {"metric": metric, "order": order, "results": rows}


def exec_generate_chart(
    chart_type: str,
    title: str,
    data: List[Dict[str, Any]],
    x_label: str = "",
    y_label: str = "",
    output_prefix: str = "poc/charts",
    filename: str = "",
) -> Dict[str, Any]:
    """Render a matplotlib PNG chart and upload it to GCS. Returns the GCS URI."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    COLORS = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#44BBA4", "#3B1F2B"]

    # Resolve filename
    if not filename:
        safe = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
        filename = safe[:80]
    if not filename.endswith(".png"):
        filename += ".png"

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#f8f9fa")
    ax.set_facecolor("#f8f9fa")

    if chart_type == "ranked_bar":
        labels = [d["label"] for d in data]
        values = [d.get("value", 0) for d in data]
        y_pos = np.arange(len(labels))
        bars = ax.barh(y_pos, values, color=COLORS[0], alpha=0.85)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.bar_label(bars, fmt="%.1f%%", padding=3)
        ax.set_xlabel(y_label or "Value (%)")

    elif chart_type == "stacked_bar":
        labels = [d["label"] for d in data]
        value_keys = [k for k in data[0] if k != "label"]
        x_pos = np.arange(len(labels))
        bottom = np.zeros(len(labels))
        for i, key in enumerate(value_keys):
            vals = np.array([d.get(key, 0) for d in data])
            ax.bar(x_pos, vals, bottom=bottom, label=key,
                   color=COLORS[i % len(COLORS)], alpha=0.85)
            bottom += vals
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels)
        ax.set_ylabel(y_label or "Percentage (%)")
        ax.set_ylim(0, 108)
        ax.legend(loc="upper right", framealpha=0.8)

    elif chart_type == "grouped_bar":
        labels = [d["label"] for d in data]
        value_keys = [k for k in data[0] if k != "label"]
        x_pos = np.arange(len(labels))
        width = 0.8 / len(value_keys)
        for i, key in enumerate(value_keys):
            offset = (i - len(value_keys) / 2 + 0.5) * width
            vals = [d.get(key, 0) for d in data]
            ax.bar(x_pos + offset, vals, width=width * 0.9,
                   label=key, color=COLORS[i % len(COLORS)], alpha=0.85)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels)
        ax.set_ylabel(y_label or "Value (%)")
        ax.legend(loc="upper right", framealpha=0.8)

    else:  # plain bar
        labels = [d["label"] for d in data]
        value_key = next((k for k in data[0] if k != "label"), "value")
        values = [d.get(value_key, 0) for d in data]
        x_pos = np.arange(len(labels))
        bars = ax.bar(x_pos, values, color=COLORS[0], alpha=0.85)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels)
        ax.set_ylabel(y_label or "Value")
        ax.bar_label(bars, fmt="%.1f", padding=3)

    ax.set_xlabel(x_label)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    gcs_path = f"{output_prefix.rstrip('/')}/{filename}"

    # Self-hostable / reproducible default: in LOCAL_DEV_MODE (the default) write the
    # chart to a local directory instead of GCS, so the benchmark runs with zero cloud
    # credentials. Only upload to GCS when explicitly out of local-dev mode; fall back
    # to a local file on any GCS error.
    if os.getenv("LOCAL_DEV_MODE", "true").lower() != "true":
        try:
            from google.cloud import storage as gcs
            bucket_name = _get_gcs_bucket()
            blob = gcs.Client().bucket(bucket_name).blob(gcs_path)
            blob.upload_from_file(buf, content_type="image/png")
            return {"gcs_uri": f"gs://{bucket_name}/{gcs_path}",
                    "filename": filename, "chart_type": chart_type}
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "Chart GCS upload failed (%s); falling back to local file", exc)

    import tempfile
    from pathlib import Path as _Path
    charts_root = _Path(os.getenv("CHART_OUTPUT_DIR",
                                   str(_Path(tempfile.gettempdir()) / "geonature_charts")))
    out_path = charts_root / gcs_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buf.getvalue())
    return {
        "gcs_uri": out_path.as_uri(),
        "filename": filename,
        "chart_type": chart_type,
    }


def exec_analyze_multi_layer(
    province: str,
    indicators: List[Dict[str, str]],
    cache_manager, user: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Analyze multiple indicators for the same province in one call (parallel raster reads)."""
    from concurrent.futures import ThreadPoolExecutor

    from agent.provinces import lookup_province

    prov = lookup_province(province)
    if prov is None:
        return {"error": f"Province '{province}' not found."}

    geometry = prov["geometry"]

    def _analyze(ind: Dict[str, str]):
        result = exec_analyze_area(
            ind["indicator"], ind["year"], ind["season"],
            geometry, cache_manager, user,
        )
        return ind["indicator"], result

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(_analyze, ind) for ind in indicators]
        results = {name: stats for name, stats in [f.result() for f in futures]}

    return {"province": prov["name"], "results": results}


def exec_toggle_layer(
    indicator: str, visible: bool, cache_manager,
) -> Dict[str, Any]:
    """Resolve layer metadata for a toggle_layer action."""
    # Try COG layers first (from cache_manager)
    all_layers = cache_manager.list_available_indicators()
    for layer in all_layers:
        info = layer if isinstance(layer, dict) else {"indicator": layer}
        if info.get("indicator") == indicator:
            return {
                "indicator": indicator,
                "year": info.get("year", ""),
                "season": info.get("season", ""),
                "visible": visible,
                "display_name": (info.get("metadata") or {}).get("description_en", indicator),
                "bounds": None,
            }

    # Fall back to WMS layers
    if indicator in WMS_LAYERS:
        wms = WMS_LAYERS[indicator]
        return {
            "indicator": indicator,
            "year": wms["year"],
            "season": wms["season"],
            "visible": visible,
            "display_name": wms["display_name"],
            "bounds": wms["bounds"],
        }

    # Fall back to vector/PMTiles display-only layers
    if indicator in VECTOR_DISPLAY_LAYERS:
        vec = VECTOR_DISPLAY_LAYERS[indicator]
        return {
            "indicator": indicator,
            "year": vec["year"],
            "season": vec["season"],
            "visible": visible,
            "display_name": vec["display_name"],
            "bounds": vec["bounds"],
        }

    return {"error": f"Layer '{indicator}' not found. Use list_layers to see available datasets."}


# ========================================
# Erosion / Spectral Index Stats
# ========================================

# Parquet cache for zonal stats (loaded once, refreshed on TTL)
_erosion_df: Optional["pd.DataFrame"] = None
_erosion_df_ts: float = 0.0
_EROSION_CACHE_TTL = 3600  # 1 hour
_EROSION_BUCKET = os.getenv("PARQUET_BUCKET", "geonatureagent_benchmark")
_EROSION_BLOB = os.getenv("PARQUET_BLOB", "data/murcia/indices/murcia_zonal_stats.parquet")

_VALID_INDICES = {"ndvi", "bsi", "ndwi", "ndbi", "msi", "savi", "nbr", "fvc"}
_MONTH_ORDER = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTH_RANK = {m: i for i, m in enumerate(_MONTH_ORDER)}


def _load_erosion_parquet() -> "pd.DataFrame":
    """Load the zonal stats Parquet from GCS, with in-memory caching."""
    import time
    global _erosion_df, _erosion_df_ts

    now = time.time()
    if _erosion_df is not None and (now - _erosion_df_ts) < _EROSION_CACHE_TTL:
        return _erosion_df

    import tempfile
    import pandas as pd

    # Prefer the parquet bundled with the repo (api/data/) so reproduction needs no GCS;
    # fall back to GCS only if it is absent.
    bundled = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "murcia_zonal_stats.parquet")
    if os.path.exists(bundled):
        _erosion_df = pd.read_parquet(bundled)
        _erosion_df_ts = now
        return _erosion_df
    local_path = os.path.join(tempfile.gettempdir(), "murcia_zonal_stats.parquet")
    try:
        from google.cloud import storage
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        client = storage.Client(project=project) if project else storage.Client()
        bucket = client.bucket(_EROSION_BUCKET)
        blob = bucket.blob(_EROSION_BLOB)
        blob.download_to_filename(local_path)
    except Exception as exc:
        if os.path.exists(local_path):
            logger.warning("GCS download failed, using cached local copy: %s", exc)
        else:
            return None

    df = pd.read_parquet(local_path)
    _erosion_df = df
    _erosion_df_ts = time.time()
    logger.info("Erosion Parquet loaded: %d rows", len(df))
    return df


def exec_query_erosion_stats(
    query_type: str,
    indices: List[str],
    municipality: str = "",
    year_start: int = 2018,
    year_end: int = 2025,
) -> Dict[str, Any]:
    """Query erosion/spectral-index zonal statistics from pre-computed Parquet.

    query_type: timeseries | ranking | seasonal
    """
    df = _load_erosion_parquet()
    if df is None:
        return {"error": "Erosion data not available. The zonal statistics Parquet has not been computed yet."}

    import pandas as pd

    # Validate indices
    valid = [idx for idx in indices if idx in _VALID_INDICES]
    if not valid:
        return {"error": f"No valid indices. Choose from: {sorted(_VALID_INDICES)}"}

    if query_type == "timeseries":
        if not municipality:
            return {"error": "municipality is required for timeseries queries"}

        mask = df["nombre"].str.lower() == municipality.lower()
        if not mask.any():
            mask = df["nombre"].str.lower().str.contains(municipality.lower(), na=False)
        if not mask.any():
            available = sorted(df["nombre"].unique().tolist())
            return {"error": f"Municipality '{municipality}' not found. Available: {available[:15]}"}

        subset = df[mask & (df["year"] >= year_start) & (df["year"] <= year_end)].copy()
        subset["_sort"] = subset["month"].map(_MONTH_RANK)
        subset = subset.sort_values(["year", "_sort"])

        cols = ["nombre", "year", "month"]
        for idx in valid:
            cols.extend([f"{idx}_{s}" for s in ("mean", "p50") if f"{idx}_{s}" in subset.columns])
        cols.append("pixel_count")
        cols = [c for c in cols if c in subset.columns]

        return {
            "query_type": "timeseries",
            "municipality": subset["nombre"].iloc[0],
            "indices": valid,
            "year_range": [year_start, year_end],
            "count": len(subset),
            "data": subset[cols].round(4).to_dict(orient="records"),
        }

    elif query_type == "ranking":
        year_data = df[(df["year"] >= year_start) & (df["year"] <= year_end)]
        if year_data.empty:
            return {"error": f"No data for years {year_start}-{year_end}"}

        rankings = {}
        for idx in valid:
            mean_col = f"{idx}_mean"
            if mean_col not in year_data.columns:
                continue
            agg = year_data.groupby("nombre")[mean_col].mean().reset_index()
            agg = agg.sort_values(mean_col, ascending=False)
            agg["rank"] = range(1, len(agg) + 1)
            rankings[idx] = agg.head(15).round(4).to_dict(orient="records")

        return {
            "query_type": "ranking",
            "year_range": [year_start, year_end],
            "indices": valid,
            "rankings": rankings,
        }

    elif query_type == "seasonal":
        if not municipality:
            # Province-level seasonal pattern
            seasonal = df[(df["year"] >= year_start) & (df["year"] <= year_end)]
        else:
            mask = df["nombre"].str.lower() == municipality.lower()
            if not mask.any():
                mask = df["nombre"].str.lower().str.contains(municipality.lower(), na=False)
            seasonal = df[mask & (df["year"] >= year_start) & (df["year"] <= year_end)]

        if seasonal.empty:
            return {"error": "No data found for the specified filters"}

        patterns = {}
        for idx in valid:
            mean_col = f"{idx}_mean"
            if mean_col not in seasonal.columns:
                continue
            monthly = seasonal.groupby("month")[mean_col].mean().reset_index()
            monthly["_sort"] = monthly["month"].map(_MONTH_RANK)
            monthly = monthly.sort_values("_sort").drop(columns=["_sort"])
            patterns[idx] = monthly.round(4).to_dict(orient="records")

        scope = municipality if municipality else "Murcia (province)"
        return {
            "query_type": "seasonal",
            "scope": scope,
            "year_range": [year_start, year_end],
            "indices": valid,
            "patterns": patterns,
        }


# ========================================
# GeoBenchX-ported tools (DAAS-46)
# ========================================


def _safe_shape(geojson: Dict[str, Any]):
    """Convert GeoJSON to a valid shapely geometry.

    Admin boundary data can contain degenerate rings (< 4 coordinates).
    shape() raises before make_valid() can run, so we strip degenerate
    rings from the raw GeoJSON first, then validate the result.
    """
    import copy
    from shapely.geometry import shape
    from shapely.validation import make_valid

    cleaned = copy.deepcopy(geojson)
    _strip_degenerate_rings(cleaned)

    try:
        geom = shape(cleaned)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Invalid geometry: {exc}. Ensure reference_aoi is valid "
            f"GeoJSON (e.g. the buffered_geometry from create_buffer)."
        ) from None

    if not geom.is_valid:
        geom = make_valid(geom)
    return geom


def _strip_degenerate_rings(geojson: Dict[str, Any]) -> None:
    """Remove polygon rings with fewer than 4 coordinate pairs in-place.

    Walks Polygon and MultiPolygon coordinate arrays and drops any ring
    that would cause shapely to raise 'A linearring requires at least 4
    coordinates'.
    """
    geom_type = geojson.get("type", "")

    if geom_type == "Polygon":
        geojson["coordinates"] = [
            ring for ring in geojson.get("coordinates", [])
            if len(ring) >= 4
        ]
    elif geom_type == "MultiPolygon":
        new_polys = []
        for polygon_coords in geojson.get("coordinates", []):
            cleaned = [ring for ring in polygon_coords if len(ring) >= 4]
            if cleaned:
                new_polys.append(cleaned)
        geojson["coordinates"] = new_polys


def _resolve_geometry(
    area_name: str, area_type: str = "province", province_hint: str = "",
) -> Optional[Dict[str, Any]]:
    """Resolve a province or municipality name to its GeoJSON geometry + metadata."""
    if area_type == "municipality":
        from admin_manager import get_admin_manager
        from agent.provinces import _normalize

        mgr = get_admin_manager()
        index = mgr.get_index()
        munis = [e for e in index if e["type"] == "municipality"]

        norm_name = _normalize(area_name)
        if province_hint:
            norm_prov = _normalize(province_hint)
            filtered = [m for m in munis if norm_prov in _normalize(m.get("province_name", ""))]
            if filtered:
                munis = filtered

        target = None
        for m in munis:
            if _normalize(m["name"]) == norm_name:
                target = m
                break
        if target is None:
            from difflib import get_close_matches
            name_map = {_normalize(m["name"]): m for m in munis}
            matches = get_close_matches(norm_name, name_map.keys(), n=1, cutoff=0.7)
            if matches:
                target = name_map[matches[0]]

        if target is None:
            return None

        feature = mgr.get_geometry("municipality", target["code"])
        if not feature or not feature.get("geometry"):
            return None
        return {
            "name": target["name"],
            "code": target["code"],
            "geometry": feature["geometry"],
        }
    else:
        from agent.provinces import lookup_province
        result = lookup_province(area_name)
        if result is None:
            return None
        return {
            "name": result["name"],
            "code": result["code"],
            "geometry": result["geometry"],
        }


def exec_create_buffer(
    area_name: str, buffer_km: float,
    area_type: str = "province", province_hint: str = "",
) -> Dict[str, Any]:
    """Create a buffer zone around a province or municipality geometry.

    Adapted from GeoBenchX create_buffer (Krechetova & Kochedykov, ACM SIGSPATIAL 2025).
    Re-implemented for GeoNatureAgent's API-based architecture.
    """
    import geopandas as gpd
    from shapely.geometry import mapping

    resolved = _resolve_geometry(area_name, area_type, province_hint)
    if resolved is None:
        return {"error": f"{area_type.title()} '{area_name}' not found."}

    geom = _safe_shape(resolved["geometry"])
    gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")

    # Reproject to EPSG:3857 (Web Mercator) for metric buffer, then back to WGS84
    gdf_merc = gdf.to_crs("EPSG:3857")
    gdf_merc["geometry"] = gdf_merc.geometry.buffer(buffer_km * 1000)
    gdf_buffered = gdf_merc.to_crs("EPSG:4326")

    buffered_geom = mapping(gdf_buffered.geometry.iloc[0])
    bounds = list(gdf_buffered.total_bounds)  # [minx, miny, maxx, maxy]

    return {
        "source_area": resolved["name"],
        "buffer_km": buffer_km,
        "buffered_geometry": buffered_geom,
        "bounds": bounds,
    }


def exec_select_features_by_spatial_relationship(
    target_type: str,
    spatial_predicates: List[str],
    reference_area: str = "",
    reference_type: str = "province",
    reference_aoi: Optional[Dict[str, Any]] = None,
    province_hint: str = "",
) -> Dict[str, Any]:
    """Select provinces or municipalities by spatial relationship with a reference area.

    Adapted from GeoBenchX select_features_by_spatial_relationship
    (Krechetova & Kochedykov, ACM SIGSPATIAL 2025).
    Re-implemented for GeoNatureAgent's admin boundary system.
    """
    import geopandas as gpd

    valid_predicates = {"intersects", "within", "contains", "touches", "overlaps"}
    predicates = [p for p in spatial_predicates if p in valid_predicates]
    if not predicates:
        return {"error": f"No valid predicates. Choose from: {sorted(valid_predicates)}"}

    # Resolve reference geometry
    if reference_aoi and reference_aoi.get("type"):
        ref_geom = _safe_shape(reference_aoi)
        ref_name = "provided AOI"
    elif reference_area:
        resolved = _resolve_geometry(reference_area, reference_type, province_hint)
        if resolved is None:
            return {"error": f"{reference_type.title()} '{reference_area}' not found."}
        ref_geom = _safe_shape(resolved["geometry"])
        ref_name = resolved["name"]
    else:
        return {"error": "Provide either reference_area or reference_aoi."}

    ref_gdf = gpd.GeoDataFrame(geometry=[ref_geom], crs="EPSG:4326")

    # Build target GeoDataFrame
    if target_type == "provinces":
        from agent.provinces import list_province_names, lookup_province
        names = list_province_names()
        rows = []
        for name in names:
            prov = lookup_province(name)
            if prov:
                rows.append({"name": prov["name"], "geometry": _safe_shape(prov["geometry"])})
    elif target_type == "municipalities":
        from admin_manager import get_admin_manager
        mgr = get_admin_manager()
        index = mgr.get_index()
        rows = []
        for entry in index:
            if entry["type"] != "municipality":
                continue
            feat = mgr.get_geometry("municipality", entry["code"])
            if feat and feat.get("geometry"):
                rows.append({"name": entry["name"], "geometry": _safe_shape(feat["geometry"])})
    else:
        return {"error": f"Unknown target_type '{target_type}'. Use 'provinces' or 'municipalities'."}

    if not rows:
        return {"error": "No target features loaded."}

    target_gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")

    # Apply spatial predicates (OR logic)
    selected = None
    for predicate in predicates:
        current = gpd.sjoin(target_gdf, ref_gdf, predicate=predicate)
        if selected is None:
            selected = current
        else:
            import pandas as pd
            selected = pd.concat([selected, current]).drop_duplicates(subset=["name"])

    if selected is None or len(selected) == 0:
        return {
            "reference": ref_name,
            "predicates": predicates,
            "target_type": target_type,
            "count": 0,
            "features": [],
        }

    features = [{"name": row["name"]} for _, row in selected.iterrows()]

    return {
        "reference": ref_name,
        "predicates": predicates,
        "target_type": target_type,
        "count": len(features),
        "features": features,
    }


def exec_get_centroids(
    area_names: List[str],
    area_type: str = "province",
    province_hint: str = "",
) -> Dict[str, Any]:
    """Get centroids of provinces or municipalities.

    Adapted from GeoBenchX get_centroids (Krechetova & Kochedykov, ACM SIGSPATIAL 2025).
    Re-implemented for GeoNatureAgent's admin boundary system.
    """
    results = []
    errors = []
    for name in area_names:
        resolved = _resolve_geometry(name, area_type, province_hint)
        if resolved is None:
            errors.append(f"'{name}' not found")
            continue
        geom = _safe_shape(resolved["geometry"])
        centroid = geom.centroid
        results.append({
            "name": resolved["name"],
            "centroid": {"lat": round(centroid.y, 6), "lon": round(centroid.x, 6)},
        })

    response: Dict[str, Any] = {"centroids": results}
    if errors:
        response["errors"] = errors
    return response


def exec_reject_task(reason: str) -> Dict[str, Any]:
    """Reject an unsolvable task with a reason.

    Adapted from GeoBenchX reject_task (Krechetova & Kochedykov, ACM SIGSPATIAL 2025).
    """
    return {
        "rejected": True,
        "reason": reason,
        "message": "This task cannot be completed with the available tools and data.",
    }
