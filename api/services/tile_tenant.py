# Copyright 2026 The GeoNatureAgent Benchmark Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Access-control helpers — open-source build.

The open-source benchmark API exposes a single public tier (no
authentication, no tenants), so this module is reduced to passthrough
helpers that accept the same call signatures used elsewhere in the codebase.
Production deployments can swap in a backend that gates layers by tenant tier.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def is_authenticated(user: Optional[Dict[str, Any]]) -> bool:
    return False


def has_layer_access(
    layer: Dict[str, Any],
    user: Optional[Dict[str, Any]] = None,
    public_guest_mode: bool = True,
) -> bool:
    return True


def filter_layers_by_access(
    layers: Iterable[Dict[str, Any]],
    user: Optional[Dict[str, Any]] = None,
    public_guest_mode: bool = True,
) -> List[Dict[str, Any]]:
    return list(layers)
