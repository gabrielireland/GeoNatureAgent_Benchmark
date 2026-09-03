# GeoNatureAgent (GNA) — MCP server

`agent/mcp_server.py` exposes the GNA toolset over the **Model Context Protocol (MCP)**,
an open standard for connecting agents to tools. It is a thin wrapper: it reuses the
existing 16 tool definitions (`tools/tools.json`) and the existing dispatcher
(`agent.tools.execute_tool`) unchanged, so the MCP path returns results byte-identical to
the FastAPI path. This makes the benchmark a reusable *substrate* — the tools stay fixed,
and any MCP-client agent is a drop-in subject-under-test.

## Run

```bash
cd api
python -m agent.mcp_server        # stdio transport
```

Then point any MCP client at that command (Claude Desktop, an OpenAI agent, the eval
harness, etc.).

## Capability scope

MCP defines three primitives — `tools`, `resources`, `prompts`. The GNA server
**implements `tools` only**, by design:

- **`tools` (implemented).** Actions the model *invokes* (`list_layers`, `analyze_area`, …).
  Advertised via `tools/list`; executed via `tools/call`.
- **`resources` (planned — Future Work).** Read-only content the client pre-loads into
  context. **Deliberately not implemented for the benchmark:** exposing data discovery as a
  *resource* would spoon-feed the catalog into context and remove the tool-selection
  behaviour we are trying to measure. Discovery is therefore kept as a *tool* (`list_layers`)
  so the agent must choose to fetch it. Resource exposure may be added later as a
  usability/reusability feature for non-eval clients.
- **`prompts` (planned — Future Work).** Reusable prompt templates / analysis workflows.
  Not implemented; **not advertised**. Per the MCP handshake, unsupported capabilities are
  simply not declared — a client that calls `prompts/*` receives the standard
  `-32601 Method not found`. We do **not** stub empty methods.

## Future Work

- Expose the layer catalog and reference data as MCP **resources** (read-only) for
  interactive/non-eval clients.
- Add MCP **prompts** for reusable analysis workflows.
- Publish over **streamable-HTTP** transport in addition to stdio.
