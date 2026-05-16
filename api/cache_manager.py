# Copyright 2026 The GeoNatureAgent Benchmark Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Layer Catalog — local-filesystem layer index.

Reads ``active-layers.json`` on startup and resolves logical layer keys
(``indicator``/``year``/``season``) to absolute local file paths.
Production deployments can swap in a cloud-storage backend; this module
keeps the open-source benchmark API self-hostable without any cloud
dependencies.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


class LayerCatalog:
    """In-memory index of available raster/JSON layers, resolved to local files."""

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        local_dev_root: Optional[Path] = None,
    ):
        # `config_dir` is where active-layers.json lives. Defaults to api/.
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).resolve().parent
        # `local_root` is where the actual data files live. Defaults to api/data/.
        self.local_root = Path(local_dev_root) if local_dev_root else self.config_dir / "data"

        self.entries: Dict[str, Any] = {}
        self.refreshed_at: Optional[datetime] = None
        self.manifest: Optional[Dict[str, Any]] = None

        self._read_manifest()
        self._index_from_manifest()

    # -- loading ------------------------------------------------------------

    def _read_manifest(self) -> None:
        manifest_file = self.config_dir / "active-layers.json"
        if not manifest_file.exists():
            _log.warning("No active-layers.json at %s", manifest_file)
            self.manifest = None
            return
        with manifest_file.open("r", encoding="utf-8") as fh:
            self.manifest = json.load(fh)
        layers = self.manifest.get("layers", []) if self.manifest else []
        active = sum(1 for ly in layers if ly.get("enabled", True))
        _log.info("Manifest loaded: %d/%d layers active", active, len(layers))

    def _index_from_manifest(self) -> bool:
        if not self.manifest:
            return False
        self.entries = {}
        for ly in self.manifest.get("layers", []):
            if not ly.get("enabled", True):
                continue
            indicator = ly["indicator"]
            year = str(ly["year"])
            season = ly["season"]
            key = f"{indicator}/{year}/{season}"
            raw_path = str(ly.get("path") or "").strip().lstrip("/\\").replace("\\", "/")
            self.entries[key] = {
                "indicator": indicator,
                "year": year,
                "season": season,
                "available": True,
                "tiles": [raw_path] if raw_path else [],
                "tile_count": 1 if raw_path else 0,
                "metadata": ly.get("metadata"),
                "path": raw_path,
                "access_tier": ly.get("access_tier", "guest"),
                "format": ly.get("format", "cog"),
            }
        self.refreshed_at = datetime.utcnow()
        _log.info("Indexed %d layers from manifest", len(self.entries))
        return True

    def reload(self) -> None:
        _log.info("Reloading layer catalog")
        self._read_manifest()
        self._index_from_manifest()

    # -- lookup -------------------------------------------------------------

    def has_layer(self, indicator: str, year: str, season: str) -> bool:
        key = f"{indicator}/{year}/{season}"
        entry = self.entries.get(key)
        return bool(entry and entry.get("available", False))

    def resolve_source(self, indicator: str, year: str, season: str) -> Optional[str]:
        """Return the absolute local path for the given layer, or ``None``."""
        key = f"{indicator}/{year}/{season}"
        entry = self.entries.get(key)
        if not entry or not entry.get("available"):
            return None
        tiles = entry.get("tiles", [])
        if not tiles:
            return None
        tile_path = tiles[0]
        local_file = self.local_root / tile_path
        return str(local_file.resolve())

    # Alias used by some code paths that expected a tile URL.
    def get_tile_url(self, indicator: str, year: str, season: str) -> Optional[str]:
        return self.resolve_source(indicator, year, season)

    def layer_metadata(self, indicator: str, year: str, season: str) -> Optional[Dict[str, Any]]:
        key = f"{indicator}/{year}/{season}"
        return self.entries.get(key)

    def indicators(self) -> List[str]:
        seen = set()
        for entry in self.entries.values():
            if entry.get("available"):
                seen.add(entry["indicator"])
        return sorted(seen)

    def years(self, indicator: Optional[str] = None) -> List[str]:
        seen = set()
        for entry in self.entries.values():
            if entry.get("available"):
                if indicator is None or entry["indicator"] == indicator:
                    seen.add(str(entry["year"]))
        return sorted(seen)

    def seasons(self, indicator: str, year: str) -> List[str]:
        result = []
        for entry in self.entries.values():
            if (
                entry.get("available")
                and entry["indicator"] == indicator
                and str(entry["year"]) == str(year)
            ):
                result.append(entry["season"])
        return sorted(result)

    def summary(self) -> Dict[str, Any]:
        return {
            "total_layers": len(self.entries),
            "indicators": list(self.indicators()),
            "years": self.years(),
            "last_updated": self.refreshed_at.isoformat() if self.refreshed_at else None,
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_catalog_singleton: Optional[LayerCatalog] = None


def get_layer_catalog(
    config_dir: Optional[Path] = None,
    local_dev_root: Optional[Path] = None,
) -> LayerCatalog:
    """Return the global LayerCatalog instance (created on first call)."""
    global _catalog_singleton
    if _catalog_singleton is None:
        _catalog_singleton = LayerCatalog(
            config_dir=config_dir,
            local_dev_root=local_dev_root,
        )
    return _catalog_singleton


# Some legacy call-sites use this alias.
get_cache_manager = get_layer_catalog
