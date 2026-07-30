---
title: MCP server
description: Run Claudeway as an MCP server. Any MCP-capable agent gains a reach_consensus tool.
---

# MCP server

Claudeway ships as a self-contained
[Model Context Protocol](https://modelcontextprotocol.io/) server. Run it
once and any MCP-capable client — **Claude Code**, **Cursor**, **Goose**,
or your own — gains two tools that produce and verify signed consensus
receipts.

This is the distribution play: instead of teaching every agent framework
how to do multi-agent agreement, you expose consensus as a single tool any
framework can call.

---

## Install

```bash
pip install claudeway[mcp]
```

Pulls `mcp>=1.0` and a small server runtime. The import is lazy — without
the extra, `import claudeway` never touches MCP.

## Run

Two transports:

```bash
claudeway-mcp            # stdio — for Claude Code, Cursor, local agents
claudeway-mcp --http     # HTTP/SSE — for remote agents (default port 8765)
```

Set `ANTHROPIC_API_KEY` in the server's environment; the server uses it to
make Claude calls on the consensus path.

## Tools exposed

### `reach_consensus`

Run a multi-agent debate and return a signed receipt.

```jsonc
{
  "question":    "Active-active Postgres or eventual consistency for payments?",
  "specialists": [
    {"name": "StrongConsistency", "role": "Distributed Systems Engineer", "perspective": "..."},
    {"name": "Operations",        "role": "SRE / Platform Lead",          "perspective": "..."},
    {"name": "Pragmatist",        "role": "Staff Engineer",               "perspective": "..."}
  ],
  "strategy":    "debate",     // or "weighted_vote" (default)
  "sign":        true          // return a signed receipt (default)
}
```

Returns the final answer, per-agent responses, agreement score, and the
signed receipt.

### `verify_consensus`

Verify a receipt's signature without re-running consensus.

```jsonc
{
  "receipt": { /* the full receipt object from reach_consensus */ }
}
```

Returns `{"valid": true}` or `{"valid": false, "reason": "..."}`. No
network calls — verification is offline and deterministic.

## Integration examples

### Claude Code

Add Claudeway as an MCP server in
`~/.config/claude-code/claude_code_config.json` (or platform equivalent):

```json
{
  "mcpServers": {
    "claudeway": {
      "command": "claudeway-mcp",
      "env":     { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

Restart Claude Code. The agent now has `reach_consensus` and
`verify_consensus` available as tools.

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "claudeway": {
      "command": "claudeway-mcp",
      "env":     { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

### Remote (HTTP/SSE)

For agents running elsewhere on your network:

```bash
claudeway-mcp --http --port 8765
```

Connect any MCP HTTP client to `http://localhost:8765/mcp`. Auth via bearer
token is supported — set `CLAUDEWAY_MCP_TOKEN` and pass
`Authorization: Bearer <token>` on requests.

## Why an MCP server?

The MCP ecosystem is at 10K+ servers and 8M downloads/month. Every framework
that adopts MCP can call Claudeway without learning the SDK, wiring graphs,
or understanding consensus strategies — they just call `reach_consensus`.

This is what makes Claudeway distribute without forcing every consumer to
rewrite their app around a new SDK. See the
[Adapters](adapters.md) page for the framework-specific paths when you want
tighter integration than a tool call.

## Reference

The MCP server is implemented in
[`claudeway.server`](api-reference.md) — see that section of the API
reference for the full request/response shapes and internal handler
structure.
