# Copyright 2026 The GeoNatureAgent Benchmark Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Province lookup for Spain — loads a static GeoJSON and provides fuzzy name matching.
"""

import json
import logging
import unicodedata
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Resolves to api/data/spain_provinces.geojson (this file lives at api/agent/).
_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "spain_provinces.geojson"

_provinces: List[Dict[str, Any]] = []
_name_index: Dict[str, int] = {}

ALIASES = {
    "vizcaya": "bizkaia/vizcaya",
    "bizkaia": "bizkaia/vizcaya",
    "guipuzcoa": "gipuzkoa/guipuzcoa",
    "guipúzcoa": "gipuzkoa/guipuzcoa",
    "gipuzkoa": "gipuzkoa/guipuzcoa",
    "alava": "araba/alava",
    "álava": "araba/alava",
    "araba": "araba/alava",
    "gerona": "girona",
    "lerida": "lleida",
    "lérida": "lleida",
    "la coruña": "a coruña",
    "orense": "ourense",
    "alicante": "alacant/alicante",
    "alacant": "alacant/alicante",
    "castellon": "castello/castellon",
    "castellón": "castello/castellon",
    "castello": "castello/castellon",
    "valencia": "valencia/valencia",
    "valència": "valencia/valencia",
    "baleares": "illes balears",
    "islas baleares": "illes balears",
    "tenerife": "santa cruz de tenerife",
    "gran canaria": "las palmas",
    "oviedo": "asturias",
    "principado de asturias": "asturias",
    "la rioja": "la rioja",
    "navarra": "navarra",
}


def _normalize(name: str) -> str:
    name = name.lower().strip()
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _load():
    global _provinces, _name_index
    if _provinces:
        return
    if not _DATA_PATH.exists():
        logger.error("Data file not found: %s", _DATA_PATH)
        return
    with _DATA_PATH.open("r", encoding="utf-8") as f:
        fc = json.load(f)
    for i, feature in enumerate(fc.get("features", [])):
        props = feature.get("properties", {})
        _provinces.append(feature)
        name = props.get("name", "")
        if name:
            _name_index[_normalize(name)] = i
            if "/" in name:
                for part in name.split("/"):
                    part = part.strip()
                    if part:
                        _name_index[_normalize(part)] = i
    for alias, canonical in ALIASES.items():
        norm_canonical = _normalize(canonical)
        if norm_canonical in _name_index:
            _name_index[_normalize(alias)] = _name_index[norm_canonical]
    logger.info("Loaded %d provinces, %d name entries", len(_provinces), len(_name_index))


def _compute_bounds(geometry: dict) -> List[float]:
    """Compute [west, south, east, north] from a GeoJSON geometry."""

    def _flatten_coords(obj):
        if isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], (int, float)):
            yield obj
        elif isinstance(obj, list):
            for item in obj:
                yield from _flatten_coords(item)

    coords = list(_flatten_coords(geometry.get("coordinates", [])))
    if not coords:
        return [-180, -90, 180, 90]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [min(lons), min(lats), max(lons), max(lats)]


def lookup_province(name: str) -> Optional[Dict[str, Any]]:
    """Look up a Spanish province by name. Returns {name, code, bounds, geometry} or None."""
    _load()
    norm = _normalize(name)

    idx = _name_index.get(norm)

    if idx is None:
        alias_target = ALIASES.get(norm)
        if alias_target:
            idx = _name_index.get(_normalize(alias_target))

    if idx is None:
        matches = get_close_matches(norm, _name_index.keys(), n=1, cutoff=0.7)
        if matches:
            idx = _name_index[matches[0]]
            logger.info("Fuzzy matched '%s' -> '%s'", name, matches[0])

    if idx is None:
        logger.warning("Province not found: '%s'", name)
        return None

    feature = _provinces[idx]
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    bounds = _compute_bounds(geom)

    return {
        "name": props.get("name", name),
        "code": props.get("code", ""),
        "bounds": bounds,
        "geometry": geom,
    }


def list_province_names() -> List[str]:
    _load()
    return [f.get("properties", {}).get("name", "") for f in _provinces]
