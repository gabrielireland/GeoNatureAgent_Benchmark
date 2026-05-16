"""Chart building, report generation, and domain enrichment data.

Contains:
- Chart color scheme and risk bands
- Auto-chart generation from categorical analyses
- Structured report building (single, comparison, combined)
- CO2 methodology enrichment (MITECO RD 214/2025)
- Pre-computed province rankings
- Province data loaders (fire, MFE, aptitude scores)
"""

import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chart / display constants
# ---------------------------------------------------------------------------

CHART_COLORS = {
    0: "#DC2626",   # Not eligible / Very high -- red
    1: "#F59E0B",   # Eligible with conditions / High -- amber
    2: "#16A34A",   # Eligible / Moderate -- green
    3: "#3B82F6",   # Low -- blue
    4: "#8B5CF6",   # Very low -- purple
    5: "#6B7280",   # Negligible -- grey
}

CONTINUOUS_RISK_BANDS = [
    (25.0, "low"),
    (50.0, "moderate"),
    (75.0, "high"),
    (101.0, "very_high"),
]

INDICATOR_DISPLAY_NAMES = {
    "co2_spain_legislation": {"en": "CO2 Absorption Suitability", "es": "Aptitud Absorcion CO2"},
    "rf_gully_probability": {"en": "Gully Erosion Probability", "es": "Probabilidad de Carcavas"},
}


# ---------------------------------------------------------------------------
# CO2 methodology enrichment (from documentation/layer_methodologies/CO2_aptitude.md)
# ---------------------------------------------------------------------------

CO2_METHODOLOGY = {
    "regulation": {
        "id": "rd_214_2025",
        "name_en": "Real Decreto 214/2025",
        "name_es": "Real Decreto 214/2025",
        "description_en": "MITECO Carbon Footprint Registry -- mandatory for ~4,000 organizations",
        "description_es": "Registro de Huella de Carbono MITECO -- obligatorio para ~4.000 organizaciones",
    },
    "criteria": [
        {
            "id": "fire_history",
            "icon": "fire",
            "name_en": "Fire History (2008-2026)",
            "name_es": "Historial de Incendios (2008-2026)",
            "source": "Copernicus EFFIS",
            "logic": "candidate",
            "description_en": "Post-fire restoration areas qualify as candidate sites",
            "description_es": "Zonas de restauracion post-incendio califican como candidatas",
            "related_layer": "burnt_areas",
        },
        {
            "id": "clc1990_baseline",
            "icon": "tree",
            "name_en": "Land Cover Baseline (CLC 1990)",
            "name_es": "Cobertura del Suelo Base (CLC 1990)",
            "source": "Copernicus Land",
            "logic": "candidate",
            "description_en": "Non-forest land in 1990 qualifies for new forest carbon projects",
            "description_es": "Terreno no forestal en 1990 es candidato para nuevos proyectos forestales de carbono",
        },
        {
            "id": "national_parks",
            "icon": "shield",
            "name_en": "National Parks",
            "name_es": "Parques Nacionales",
            "source": "MITECO",
            "logic": "exclusion",
            "description_en": "Hard exclusion -- projects cannot register inside National Parks",
            "description_es": "Exclusion estricta -- los proyectos no pueden registrarse dentro de Parques Nacionales",
        },
        {
            "id": "natura2000",
            "icon": "leaf",
            "name_en": "Natura 2000 Network",
            "name_es": "Red Natura 2000",
            "source": "MITECO",
            "logic": "conditional",
            "description_en": "Sites require compatibility verification with management plans",
            "description_es": "Los sitios requieren verificacion de compatibilidad con planes de gestion",
        },
        {
            "id": "clc2018_urban",
            "icon": "building",
            "name_en": "Urban Exclusion (CLC 2018)",
            "name_es": "Exclusion Urbana (CLC 2018)",
            "source": "Copernicus Land",
            "logic": "exclusion",
            "description_en": "Urban and artificial surfaces are excluded",
            "description_es": "Las superficies urbanas y artificiales quedan excluidas",
        },
    ],
    "formula_en": "APTITUDE = min(Parks, Natura2000, Non-urban, max(Fire, Non-forest 1990))",
    "formula_es": "APTITUD = min(P.Nacionales, Natura2000, NoUrbano, max(Incendio, NoForestal 1990))",
    "next_steps_en": [
        "Overlay cadastral boundaries to identify specific parcels",
        "Verify conditional zones with MITECO management plan compatibility",
        "Begin formal MITECO registration process for eligible parcels",
        "Select reforestation species based on local forest inventory (MFE)",
    ],
    "next_steps_es": [
        "Superponer limites catastrales para identificar parcelas concretas",
        "Verificar zonas condicionadas con compatibilidad de planes de gestion MITECO",
        "Iniciar proceso formal de inscripcion MITECO para parcelas elegibles",
        "Seleccionar especies de reforestacion segun inventario forestal local (MFE)",
    ],
}

CO2_PROVINCE_RANKINGS = [
    ("Ciudad Real", 78.9), ("Sevilla", 73.2), ("Albacete", 72.9),
    ("Badajoz", 69.1), ("Valladolid", 69.1), ("Salamanca", 68.9),
    ("Murcia", 68.5), ("Cordoba", 68.4), ("Malaga", 67.8),
    ("Toledo", 67.5), ("Granada", 67.3), ("Cuenca", 67.2),
    ("Ourense", 67.2), ("Palencia", 66.9), ("Zaragoza", 66.4),
    ("Burgos", 64.3), ("Zamora", 64.1), ("Alicante", 63.9),
    ("Lugo", 63.2), ("Almeria", 62.4), ("Soria", 61.2),
    ("Pontevedra", 60.2), ("Segovia", 60.0), ("Illes Balears", 59.5),
    ("Caceres", 58.8), ("Jaen", 58.4), ("Teruel", 58.3),
    ("A Coruna", 57.9), ("Cadiz", 56.8), ("Tarragona", 55.7),
    ("Huesca", 55.4), ("La Rioja", 54.7), ("Guadalajara", 53.5),
    ("Navarra", 53.3), ("Leon", 52.3), ("Avila", 52.1),
    ("Lleida", 50.7), ("Asturias", 49.9), ("Valencia", 49.1),
    ("Las Palmas", 49.0), ("Alava", 48.0), ("Cantabria", 48.0),
    ("Castellon", 47.8), ("Madrid", 44.7), ("Huelva", 42.7),
    ("Santa Cruz de Tenerife", 42.4), ("Bizkaia", 40.9),
    ("Barcelona", 39.0), ("Girona", 34.7), ("Gipuzkoa", 33.5),
    ("Melilla", 25.1), ("Ceuta", 20.8),
]


# ---------------------------------------------------------------------------
# Pre-computed province data loaders
# ---------------------------------------------------------------------------

def _load_province_data(filename: str) -> dict:
    """Load a JSON data file from api/agent/data/ (vendored, open-source build)."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", filename)
        if not os.path.isfile(path):
            logger.warning("[AGENT] Data file not found: %s", path)
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("[AGENT] Failed to load %s: %s", filename, exc)
        return {}


FIRE_PROVINCE_STATS = _load_province_data("fire_province_stats.json")
MFE_PROVINCE_STATS = _load_province_data("mfe_province_stats.json")
CO2_APTITUDE_SCORES = _load_province_data("co2_aptitude_scores.json")


def get_co2_ranking(name: str) -> Optional[Dict]:
    """Look up a province in the CO2 eligibility ranking."""
    from agent.provinces import _normalize
    norm = _normalize(name)
    for i, (prov, pct) in enumerate(CO2_PROVINCE_RANKINGS):
        if _normalize(prov) == norm:
            return {"position": i + 1, "total": len(CO2_PROVINCE_RANKINGS), "eligible_pct": pct}
    return None


def _get_fire_stats(name: str) -> Optional[Dict]:
    from agent.provinces import _normalize
    norm = _normalize(name)
    for prov, stats in FIRE_PROVINCE_STATS.items():
        if _normalize(prov) == norm:
            return stats
    return None


def _get_mfe_stats(name: str) -> Optional[Dict]:
    from agent.provinces import _normalize
    norm = _normalize(name)
    for prov, stats in MFE_PROVINCE_STATS.items():
        if _normalize(prov) == norm:
            return stats
    return None


def _get_aptitude_score(name: str) -> Optional[Dict]:
    from agent.provinces import _normalize
    norm = _normalize(name)
    for prov, score in CO2_APTITUDE_SCORES.items():
        if _normalize(prov) == norm:
            return score
    return None


# ---------------------------------------------------------------------------
# Chart and report builders
# ---------------------------------------------------------------------------

def build_chart(analysis_results: List[Dict]) -> Optional[Dict]:
    """Auto-generate a bar chart from categorical analyses (single or comparison)."""
    categorical = [
        r for r in analysis_results
        if r["result"].get("type") == "categorical" and "breakdown" in r["result"]
    ]
    if not categorical:
        return None

    is_comparison = len(categorical) >= 2
    bars = []
    for r in categorical:
        label = r["label"]
        breakdown = r["result"]["breakdown"]
        for entry in breakdown:
            bars.append({
                "label": f"{label}: {entry['label']}" if is_comparison else entry["label"],
                "value": entry["percentage"],
                "color": CHART_COLORS.get(entry.get("value"), "#6B7280"),
            })

    if not bars:
        return None

    title = "Comparison" if is_comparison else categorical[0]["label"]
    return {
        "type": "chart",
        "data": {
            "title": title,
            "bars": bars,
        },
    }


def build_report(analysis_results: List[Dict], lang: str = "en") -> Optional[Dict]:
    """Build a structured report action from all analysis results (categorical + continuous)."""
    from agent.tools.executors import INDICATOR_UNITS

    if not analysis_results:
        return None

    valid = [r for r in analysis_results if "error" not in r.get("result", {})]
    if not valid:
        return None

    areas = []
    indicators_seen = set()
    area_labels_seen = set()

    for r in valid:
        label = r["label"]
        result = r["result"]
        ti = r.get("tool_input", {})
        indicator = ti.get("indicator", "")
        year = ti.get("year", "")
        season = ti.get("season", "")
        indicators_seen.add(indicator)
        area_labels_seen.add(label)

        display_names = INDICATOR_DISPLAY_NAMES.get(indicator, {})
        indicator_label = display_names.get("en", indicator.replace("_", " ").title())

        if result.get("type") == "categorical":
            breakdown = []
            for entry in result.get("breakdown", []):
                breakdown.append({
                    "value": entry["value"],
                    "label": entry["label"],
                    "pixel_count": entry.get("pixel_count", 0),
                    "percentage": entry["percentage"],
                    "color": CHART_COLORS.get(entry.get("value"), "#6B7280"),
                })
            area_entry = {
                "label": indicator_label,
                "indicator": indicator,
                "year": year,
                "season": season,
                "area_name": label,
                "result_type": "categorical",
                "total_pixels": result.get("total_pixels", 0),
                "breakdown": breakdown,
            }
            # Enrich CO2 areas with methodology context
            if indicator == "co2_spain_legislation":
                area_entry["methodology"] = CO2_METHODOLOGY
                ranking = get_co2_ranking(label)
                if ranking:
                    area_entry["ranking"] = ranking
                apt = _get_aptitude_score(label)
                if apt:
                    area_entry["aptitude_score"] = apt
                fire = _get_fire_stats(label)
                if fire:
                    area_entry["fire_stats"] = fire
                mfe = _get_mfe_stats(label)
                if mfe:
                    area_entry["mfe_stats"] = mfe
            areas.append(area_entry)
        elif result.get("type") == "continuous":
            scaled = result.get("statistics", {})
            unit = scaled.get("unit", INDICATOR_UNITS.get(indicator, ""))
            scaled["unit"] = unit

            mean_val = scaled.get("mean", 0.0)
            risk_band = "very_high"
            for threshold, band in CONTINUOUS_RISK_BANDS:
                if mean_val < threshold:
                    risk_band = band
                    break

            areas.append({
                "label": indicator_label,
                "indicator": indicator,
                "year": year,
                "season": season,
                "area_name": label,
                "result_type": "continuous",
                "total_pixels": result.get("total_pixels", 0),
                "statistics": scaled,
                "risk_band": risk_band,
            })

    if not areas:
        return None

    # Determine report type
    n_areas = len(area_labels_seen)
    n_indicators = len(indicators_seen)
    if n_indicators > 1 and n_areas <= 1:
        report_type = "combined"
    elif n_areas > 1:
        report_type = "comparison"
    else:
        report_type = "single"

    area_names = list(dict.fromkeys(a["area_name"] for a in areas))
    title = " vs. ".join(area_names) if len(area_names) <= 3 else f"{len(area_names)} areas"

    # Comparison table for multi-area categorical
    comparison_table = None
    if report_type == "comparison":
        cat_areas = [a for a in areas if a["result_type"] == "categorical"]
        if len(cat_areas) >= 2:
            all_cats = []
            seen = set()
            for area in cat_areas:
                for entry in area["breakdown"]:
                    if entry["label"] not in seen:
                        all_cats.append({"label": entry["label"], "color": entry["color"]})
                        seen.add(entry["label"])
            rows = []
            for cat in all_cats:
                values = []
                for area in cat_areas:
                    match = next((e for e in area["breakdown"] if e["label"] == cat["label"]), None)
                    values.append(match["percentage"] if match else 0.0)
                rows.append({"label": cat["label"], "color": cat["color"], "values": values})
            comparison_table = {
                "headers": ["Category"] + [a["area_name"] for a in cat_areas],
                "rows": rows,
            }

    return {
        "type": "report",
        "data": {
            "report_type": report_type,
            "title": title,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "areas": areas,
            "comparison_table": comparison_table,
            "lang": lang,
        },
    }
