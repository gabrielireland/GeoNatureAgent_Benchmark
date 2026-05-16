# Copyright 2026 The GeoNatureAgent Benchmark Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Event-logger stub — open-source build.

Writes agent query/feedback events to a local JSONL file under ./logs/ if
the directory exists; otherwise the call is a silent no-op. Production
deployments can swap in a backend that ships events to durable storage.

The call signatures match those used elsewhere in the codebase so the
agent module need not be modified.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_LOG_DIR = Path(os.environ.get("AGENT_LOG_DIR", "./logs"))


def generate_query_id() -> str:
    return uuid.uuid4().hex[:16]


def _write_jsonl(filename: str, event: Dict[str, Any]) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = _LOG_DIR / filename
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Logging must never crash the agent loop.
        pass


def log_query_event(event: Dict[str, Any]) -> None:
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    _write_jsonl("queries.jsonl", event)


def log_feedback_event(event: Dict[str, Any]) -> None:
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    _write_jsonl("feedback.jsonl", event)
