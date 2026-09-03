"""MCP server — exposes the GeoNatureAgent (GNA) toolset over the Model Context Protocol.

This is a THIN WRAPPER, not a rewrite. It reuses, untouched:
  - the 16 tool definitions in ``tools/tools.json`` (already ``name``/``description``/
    ``input_schema`` — i.e. MCP's exact tool shape), and
  - the existing dispatcher ``agent.tools.execute_tool`` (Pydantic validation + executors).

The FastAPI app keeps working exactly as before; this simply publishes the SAME tools
over a standard protocol so ANY MCP client (Claude Desktop, an OpenAI agent, the eval
harness) can drive the identical tool layer. That is what makes the benchmark a reusable
*substrate*: the tools are fixed, only the agent-under-test changes.

Run (stdio transport):
    python -m agent.mcp_server
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Put the `api/` dir on the path so `agent.tools` and `cache_manager` import the same
# way they do under the FastAPI app (whose package root is `api/`).
_API_DIR = Path(__file__).resolve().parents[1]
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from agent.tools import execute_tool          # the EXISTING dispatcher — unchanged
from cache_manager import get_cache_manager    # the EXISTING singleton — unchanged

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

_TOOLS_PATH = Path(__file__).resolve().parent / "tools" / "tools.json"


def _load_tool_defs() -> list[dict]:
    """Load the 16 tool definitions verbatim from tools.json."""
    raw = json.loads(_TOOLS_PATH.read_text(encoding="utf-8"))
    tools = raw if isinstance(raw, list) else raw.get("tools", [])
    if not tools:
        raise RuntimeError(f"No tools found in {_TOOLS_PATH}")
    return tools


TOOL_DEFS = _load_tool_defs()

app = Server("geonatureagent")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Advertise the GNA toolset — a 1:1 mapping from tools.json to MCP Tool objects."""
    return [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["input_schema"],   # our key is input_schema; MCP field is inputSchema
        )
        for t in TOOL_DEFS
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Route an MCP tool call through the SAME dispatcher the FastAPI agent uses.

    execute_tool() already does Pydantic validation, executor dispatch, and returns a
    JSON string, so the MCP path and the HTTP path produce identical results.
    """
    cache_manager = get_cache_manager()
    # Executors are synchronous (rasterio, file I/O); run off the event loop.
    result_json = await asyncio.to_thread(
        execute_tool, name, arguments or {}, cache_manager, None
    )
    return [types.TextContent(type="text", text=result_json)]


async def _main() -> None:
    logger.info("Starting GeoNatureAgent MCP server (%d tools) over stdio", len(TOOL_DEFS))
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
