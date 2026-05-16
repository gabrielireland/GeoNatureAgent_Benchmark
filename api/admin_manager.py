# Copyright 2026 The GeoNatureAgent Benchmark Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Spanish administrative boundaries — data loader and geometry provider.

Loads the admin index (CCAA / Province / Municipality hierarchy) and serves
geometry on demand from per-province GeoJSON files.

All data generated from GISCO (Eurostat).
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("geonatureagent.admin")

# Data lives under api/data/ (this file lives at api/).
DATA_DIR = Path(__file__).resolve().parent / "data"
INDEX_PATH = DATA_DIR / "spain_admin_index.json"
CCAA_PATH = DATA_DIR / "spain_ccaa.geojson"
PROVINCES_PATH = DATA_DIR / "spain_provinces.geojson"
MUNI_DIR = DATA_DIR / "municipalities"


class AdminManager:
    """Singleton that loads and caches Spanish admin boundary data."""

    def __init__(self):
        self._index: list | None = None
        self._ccaa_geojson: dict | None = None
        self._provinces_geojson: dict | None = None
        self._muni_cache: dict[str, dict] = {}

    def get_index(self) -> list:
        if self._index is None:
            with open(INDEX_PATH, encoding="utf-8") as f:
                self._index = json.load(f)
            logger.info("Loaded admin index: %d entries", len(self._index))
        return self._index

    def get_geometry(self, admin_type: str, code: str) -> Optional[dict]:
        if admin_type == "ccaa":
            return self._get_ccaa_feature(code)
        elif admin_type == "province":
            return self._get_province_feature(code)
        elif admin_type == "municipality":
            return self._get_municipality_feature(code)
        return None

    def _get_ccaa_feature(self, code: str) -> Optional[dict]:
        if self._ccaa_geojson is None:
            with open(CCAA_PATH, encoding="utf-8") as f:
                self._ccaa_geojson = json.load(f)
        for feat in self._ccaa_geojson.get("features", []):
            if feat["properties"].get("code") == code:
                return feat
        return None

    def _get_province_feature(self, code: str) -> Optional[dict]:
        if self._provinces_geojson is None:
            with open(PROVINCES_PATH, encoding="utf-8") as f:
                self._provinces_geojson = json.load(f)
        for feat in self._provinces_geojson.get("features", []):
            if feat["properties"].get("code") == code:
                return feat
        return None

    def _get_municipality_feature(self, code: str) -> Optional[dict]:
        prov_code = code[:2]
        if prov_code not in self._muni_cache:
            path = MUNI_DIR / f"{prov_code}.geojson"
            if not path.exists():
                return None
            with open(path, encoding="utf-8") as f:
                self._muni_cache[prov_code] = json.load(f)
            logger.info("Loaded municipality geometries for province %s", prov_code)
        fc = self._muni_cache[prov_code]
        for feat in fc.get("features", []):
            if feat["properties"].get("code") == code:
                return feat
        return None


_instance: AdminManager | None = None


def get_admin_manager() -> AdminManager:
    global _instance
    if _instance is None:
        _instance = AdminManager()
    return _instance
