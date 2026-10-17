---
title: MCP demo
description: Five minutes from pip install to a verifiable multi-agent decision.
---

# MCP demo: decision to verifiable receipt in 5 minutes

The headline path: `pip install tractum[mcp]`, wire the server into
Claude Code, run a decision through it, verify the signed receipt. Every
command below works against the current code.

> **Launch note:** the PyPI package `tractum` is being published alongside
> this release. Until it lands, install from the repo:
> `pip install git+https://github.com/JordanNewell/tractum.git#egg=tractum[mcp]`.

---

## Step 1 — install (30 seconds)

```bash
pip install tractum[mcp]
```

This installs the SDK plus the MCP server runtime and the `tractum-mcp`
console script. Check it:

```bash
tractum-mcp --help
```

## Step 2 — see it work, keyless (30 seconds)

You don't need an API key to understand what Tractum produces. The demo
runs a 3-agent decision offline (stub agents, real cryptography), then
verifies the receipt through the server's own `verify_consensus` tool:

```bash
python examples/mcp_demo.py
```

Output (abridged):

```text
Step 2 - sign the receipt (same path as tractum-mcp)
payload:    v2 (3 signed statements)
payload hash: e3735ac3a873240e251c6400c5236da843cc9cf07b0cf38437d0e8a34f7130ba
quorum:     k-of-n = 3-of-3
algorithm:  ed25519
operator pubkey: c57e62e66fac747247d54ec9...
signature:  8ca3eaa231d725818105b7944407a97e...

Step 3 - verify (MCP verify_consensus)
(verified through the tractum MCP server's verify_consensus tool)
valid:            True
aggregate sig:    True (pinned to operator key)
quorum met:       3/3 of 3 statements
  - ShipIt: valid
  - Reliability: valid
  - Security: valid
```

With `ANTHROPIC_API_KEY` set, the same script runs real Claude specialists
instead of stubs — the receipt and verification are identical in shape.

## Step 3 — wire the server into Claude Code (1 minute)

Set your keys, then register the server. Either the CLI:

```bash
claude mcp add tractum \
  --env ANTHROPIC_API_KEY=sk-ant-... \
  -- tractum-mcp
```

or a `.mcp.json` at the project root:

```json
{
  "mcpServers": {
    "tractum": {
      "command": "tractum-mcp",
      "args": [],
      "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

Restart Claude Code (or run `/mcp` to check the server is connected). You
now have two tools: `reach_consensus` and `verify_consensus`.

If `tractum-mcp` lives in a venv, point `command` at the venv's absolute
path (e.g. `.venv/Scripts/tractum-mcp.exe` on Windows,
`.venv/bin/tractum-mcp` elsewhere) — the child process won't inherit
your activated venv.

## Step 4 — run a decision through it (1 minute)

Ask Claude Code:

> Use reach_consensus to decide: should our new MCP server GA in the next
> release or ship behind a feature flag? Specialists: a product lead, an
> SRE, and a security engineer.

Claude Code calls the tool with the three specialists; the server runs the
swarm and returns a signed receipt — final answer, per-agent responses
(each with its own cryptographic statement), agreement score, and the
Ed25519 signature.

## Step 5 — verify the receipt (1 minute)

Follow up in the same session:

> Run verify_consensus on that receipt. Pin the operator key to
> `<public_key from the receipt>`.

The tool re-checks everything offline — no network, deterministic:

```json
{
  "valid": true,
  "aggregate_valid": true,
  "quorum": 3,
  "valid_statements": 3,
  "total_statements": 3,
  "statements": [
    { "agent": "ShipIt",      "valid": true, "reason": "" },
    { "agent": "Reliability", "valid": true, "reason": "" },
    { "agent": "Security",    "valid": true, "reason": "" }
  ]
}
```

Pin matters: without `expected_operator_pubkey`, anyone can re-sign a
doctored payload with their own key and it would still read `valid`.
Per-statement failures come back named (`key-mismatch`,
`task-id-mismatch`, `response-mismatch:answer`, `signature-invalid`), so a
tampered receipt tells you *what* broke, not just that it broke.

## One setting worth knowing: the signing key

Out of the box the server signs every receipt with a fresh **ephemeral**
keypair — the receipt is signed and internally verifiable, but the key
dies with the response, so a verifier must take the operator public key
from the receipt itself. For receipts a verifier can pin *ahead of time*,
give the server a stable operator key. Generate one:

```bash
python -c "from tractum import Ed25519Backend; p, u = Ed25519Backend().generate_keypair(); print(p, u)"
```

and put the private key in the server env:

```json
"env": { "ANTHROPIC_API_KEY": "sk-ant-...", "TRACTUM_SIGNING_KEY": "<private key>" }
```

Now every receipt from this server is signed by the same key, and verifiers
can pin it once and trust it forever. Keep the private key out of anything
committed; per-project `.mcp.json` users should reference it via an
environment variable their shell already exports instead of pasting it in.

Deployments that must never ship an ephemeral-signed receipt set
`TRACTUM_REQUIRE_PINNED_KEY=1`: without a configured key the server fails
the call loudly instead of signing with a throwaway key.

Offline wiring and demos don't need an API key at all — set
`TRACTUM_MCP_DRY_RUN=1` (or pass `"dry_run": true`) to run deterministic
stub agents through the exact same signing and verification path.

---

## What just happened

Three agents disagreed, weighted-voted, and each agent signed its own
stance. The receipt is a k-of-n multi-sig over machine judgment — hand it
to an auditor, a teammate, or a future process, and anyone can prove it
wasn't edited in between. See [MCP server](mcp-server.md) for the full
tool reference and [Transports](transports.md) for the JSON / W3C VC /
Nostr renderings of the same receipt.
