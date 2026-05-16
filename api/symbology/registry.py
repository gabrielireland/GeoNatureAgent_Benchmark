# Copyright 2026 The GeoNatureAgent Benchmark Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Style definitions for raster layer rendering and legend generation.

Each layer is described by a ``LayerStyle`` containing ordered ``ColorEntry``
items that map integer pixel values to RGBA colours. Styles are loaded from
``api/symbology/symbologies.json`` and indexed by id plus optional suffix-based
aliases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ColorEntry(BaseModel):
    """Single value-to-colour mapping inside a layer style."""

    model_config = {"populate_by_name": True}

    value: int
    label: str
    rgba: tuple[int, int, int, int] = Field(
        ..., description="RGBA tuple with components in the 0-255 range"
    )
    visible: bool = Field(True, alias="show_in_legend")
    header: bool = Field(False, alias="is_header")

    @field_validator("rgba")
    @classmethod
    def check_channels(cls, v: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        if len(v) != 4:
            raise ValueError("rgba must have exactly 4 channels")
        out = []
        for ch in v:
            ch_int = int(ch)
            if ch_int < 0 or ch_int > 255:
                raise ValueError("rgba channel must be 0-255")
            out.append(ch_int)
        return tuple(out)  # type: ignore[return-value]


class LayerStyle(BaseModel):
    """Complete colour scheme for one raster indicator."""

    model_config = {"populate_by_name": True}

    id: str
    name: Optional[str] = None
    type: Literal["categorical", "continuous", "rgb"] = "categorical"
    aliases: List[str] = Field(default_factory=list)
    entries: List[ColorEntry]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    mono_band: bool = Field(False, alias="force_single_band")

    def pixel_colors(self) -> Dict[int, tuple[int, int, int, int]]:
        return {e.value: e.rgba for e in self.entries if not e.header}

    def defined_values(self) -> List[int]:
        return [e.value for e in self.entries]

    def as_legend(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        has_hdrs = any(e.header for e in self.entries)
        ordered = self.entries if has_hdrs else sorted(self.entries, key=lambda e: e.value)
        for entry in ordered:
            if not entry.visible:
                continue
            if entry.header:
                items.append({"label": entry.label, "isHeader": True})
                continue
            r, g, b, _a = entry.rgba
            items.append(
                {
                    "value": entry.value,
                    "label": entry.label,
                    "color": f"rgb({r},{g},{b})",
                }
            )
        return items


class StyleSheet(BaseModel):
    symbologies: List[LayerStyle] = Field(default_factory=list)


# Resolves to api/symbology/symbologies.json (this file lives at api/symbology/).
_STYLES_PATH = Path(__file__).resolve().parent / "symbologies.json"
_active_path = _STYLES_PATH
_styles: Dict[str, LayerStyle] = {}
_name_map: Dict[str, str] = {}
_initialized = False


def _clean_key(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    return cleaned or None


def load_styles(config_path: Optional[str | Path] = None, *, reload: bool = False) -> None:
    global _active_path, _initialized
    path = Path(config_path) if config_path else _active_path
    if _initialized and not reload and config_path is None:
        return
    if not path.exists():
        raise FileNotFoundError(f"Stylesheet not found at {path}")
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    sheet = StyleSheet(**payload)

    _styles.clear()
    _name_map.clear()

    for style in sheet.symbologies:
        _styles[style.id] = style
        key = _clean_key(style.id)
        if key:
            _name_map[key] = style.id
        for alias in style.aliases:
            alias_key = _clean_key(alias)
            if alias_key:
                _name_map[alias_key] = style.id

    _active_path = path
    _initialized = True


def _auto_init() -> None:
    if not _initialized:
        load_styles()


def resolve_style(identifier: Optional[str]) -> Optional[LayerStyle]:
    _auto_init()
    cleaned = _clean_key(identifier)
    if not cleaned:
        return None
    style_id = _name_map.get(cleaned)
    if not style_id:
        by_length = sorted(_name_map.keys(), key=len, reverse=True)
        for alias in by_length:
            if alias and cleaned.startswith(f"{alias}_"):
                style_id = _name_map.get(alias)
                break
    if not style_id:
        return None
    return _styles.get(style_id)


def legend_for(identifier: Optional[str]) -> List[Dict[str, Any]]:
    style = resolve_style(identifier)
    if not style:
        return []
    return style.as_legend()


# Backward-compat aliases used by existing call-sites.
SymbologyEntry = ColorEntry
SymbologyDefinition = LayerStyle
SymbologyCatalog = StyleSheet
load_catalog = load_styles
get_symbology = resolve_style
get_legend_items = legend_for
