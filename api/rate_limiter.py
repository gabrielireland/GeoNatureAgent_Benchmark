# Copyright 2026 The GeoNatureAgent Benchmark Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Rate-limiter stub — open-source build.

The open-source benchmark API has no notion of tenants and is run by the
user on their own infrastructure, so quota enforcement is intentionally a
no-op. Production deployments should swap in a backend that records usage
and rejects requests above their own thresholds.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

TIERS: Dict[str, Dict[str, Any]] = {
    "public": {"requests_per_day": None, "tokens_per_day": None},
}


def check_rate_limit(
    user: Optional[Dict[str, Any]] = None,
    *args,
    **kwargs,
) -> Tuple[bool, Dict[str, Any]]:
    """Always permit. Returns (allowed, metadata)."""
    return True, {"tier": "public", "remaining": None}


def record_token_usage(
    user: Optional[Dict[str, Any]] = None,
    tokens: int = 0,
    *args,
    **kwargs,
) -> None:
    """No-op in the open-source build."""
    return None
