"""GeoNatureAgent — modular agentic advisor for geospatial analysis.

Public API:
    run_agent()      -- Main agent loop (tool-use orchestration)
    session_store    -- In-memory session store (for benchmarks)

Module layout:
    agent.py         -- Main loop (parallel execution, LLM client injection)
    security.py      -- Input/output sanitization, language detection
    session.py       -- Session store with TTL + LRU eviction
    charts.py        -- Chart/report generation, CO2 methodology data
    tools/           -- Tool registry, Pydantic models, executor functions
    prompts/         -- Versioned system prompts (v1.md, v2.md, v3.md — v3 is the default)
"""

from agent.agent import run_agent
from agent.session import session_store

__all__ = ["run_agent", "session_store"]
