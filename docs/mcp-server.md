---
title: MCP server
description: Run Tractum as an MCP server. Any MCP-capable agent gains a reach_consensus tool.
---

# MCP server

Tractum ships as a self-contained
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
pip install tractum[mcp]
```

Pulls `mcp>=1.0` and a small server runtime. The import is lazy — without
the extra, `import tractum` never touches MCP.

## Run

Two transports:

```bash
tractum-mcp            # stdio — for Claude Code, Cursor, local agents
tractum-mcp --http     # HTTP/SSE — for remote agents (default port 8765)
```

Set `ANTHROPIC_API_KEY` in the server's environment; the server uses it to
make Claude calls on the consensus path. The server has no built-in auth
for the HTTP transport — bind it to loopback or put it behind your own
reverse proxy / tunnel auth before exposing it beyond localhost.

## Environment variables

| Variable | Effect |
|----------|--------|
| `ANTHROPIC_API_KEY` | Claude API key for live consensus runs. |
| `TRACTUM_SIGNING_KEY` | Hex Ed25519 **private** key. When set, every receipt is signed by this stable operator key — verifiers pin the matching public key once. |
| `TRACTUM_REQUIRE_PINNED_KEY` | `1`/`true`: refuse to sign unless `TRACTUM_SIGNING_KEY` is set. For deployments that must never ship an ephemeral-signed receipt. |
| `TRACTUM_MCP_DRY_RUN` | `1`/`true`: every `reach_consensus` call runs offline stub agents (see below). |

## Tools exposed

### `reach_consensus`

Run a multi-agent swarm and return a signed receipt.

```jsonc
{
  "question":    "Active-active Postgres or eventual consistency for payments?",
  "specialists": [
    {"name": "StrongConsistency", "role": "Distributed Systems Engineer", "instructions": "..."},
    {"name": "Operations",        "role": "SRE / Platform Lead",          "instructions": "..."},
    {"name": "Pragmatist",        "role": "Staff Engineer",               "instructions": "..."}
  ],
  "strategy":    "debate",     // or "weighted_vote" (default)
  "dry_run":     false         // offline stub agents, no API calls (see below)
}
```

Returns the final answer, per-agent responses, agreement score, and the
signed receipt.

**Signing.** With `TRACTUM_SIGNING_KEY` set, the receipt is signed by that
stable key. Without it, the server signs with a fresh **ephemeral**
keypair per receipt: the receipt is still fully signed and verifiable, but
the key exists only for that response — verifiers take the operator
public key from the response itself (the `public_key` field; metadata
`operator_key: "ephemeral"` marks the mode). For any deployment where
verifiers pin the key ahead of time, set `TRACTUM_SIGNING_KEY`.

### `verify_consensus`

Verify a receipt end to end without re-running consensus: aggregate
signature, every per-agent statement signature, statement/response
consistency, and the quorum count.

```jsonc
{
  "receipt": { /* the full receipt object from reach_consensus */ },
  // optional pinning — see below
  "expected_operator_pubkey": "hex…",
  "expected_agent_pubkeys": { "Alice": "hex…", "Bob": "hex…" }
}
```

Returns `{"valid": true/false, "aggregate_valid": …, "quorum": k,
"valid_statements": m, "total_statements": n, "statements": [{"agent",
"valid", "reason"}, …]}`. No network calls — verification is offline and
deterministic.

Pinning matters: without `expected_operator_pubkey`, anyone can re-sign a
doctored payload with their own key and it verifies "valid". Pin the keys
you know, and per-statement failures come back named (`key-mismatch`,
`task-id-mismatch`, `response-mismatch:answer`, `signature-invalid`).
`expected_agent_pubkeys` does the same per agent: it checks that each
agent's statement was signed by the key you know for that agent, not just
by *some* key the payload carries.

## Dry-run mode

`TRACTUM_MCP_DRY_RUN=1` (or `"dry_run": true` on the call) replaces the
live Claude swarm with deterministic offline stub agents — real per-agent
keypairs, real statement signatures, no intelligence, no API calls. The
receipt self-identifies as a dry run (swarm name `mcp-consensus-dry-run`,
stub answers, metadata `dry_run: "true"`), and `verify_consensus` happily
verifies it — dry-run receipts are for wiring, testing, and demos, never
decisions.

## Integration examples

### Claude Code

Add Tractum as an MCP server in
`~/.config/claude-code/claude_code_config.json` (or platform equivalent):

```json
{
  "mcpServers": {
    "tractum": {
      "command": "tractum-mcp",
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
    "tractum": {
      "command": "tractum-mcp",
      "env":     { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

### Remote (HTTP/SSE)

For agents running elsewhere on your network:

```bash
tractum-mcp --http --port 8765
```

Connect any MCP HTTP client to `http://localhost:8765/mcp`.

## Why an MCP server?

The MCP ecosystem is at 10K+ servers and 8M downloads/month. Every framework
that adopts MCP can call Tractum without learning the SDK, wiring graphs,
or understanding consensus strategies — they just call `reach_consensus`.

This is what makes Tractum distribute without forcing every consumer to
rewrite their app around a new SDK. See the
[Adapters](adapters.md) page for the framework-specific paths when you want
tighter integration than a tool call.

## Reference

The MCP server is implemented in
[`tractum.server`](api-reference.md) — see that section of the API
reference for the full request/response shapes and internal handler
structure.
