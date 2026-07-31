---
title: Configuration
description: Every knob in the SDK — AgentConfig, SwarmConfig, consensus strategies, signature backends, MCP server CLI, environment variables, and optional extras.
---

# Configuration

Every public knob in the SDK. Defaults are sensible for most cases — only deviate when you have a reason.

---

## `AgentConfig`

A single Claude agent. You usually pass these into `SwarmConfig.agents` rather than constructing `Agent` directly.

```python
from claudeway import AgentConfig

AgentConfig(
    name="Security",
    role="Adversarial reviewer",
    instructions="You look for ways this could go wrong.",
)
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | `str` | (required) | Display name; lands on the receipt under each agent's response. |
| `role` | `str` | (required) | One-line role description; injected into the system prompt. |
| `instructions` | `str` | (required) | Free-form system-prompt body. |
| `model` | `str` | `"claude-3-5-sonnet-20241022"` | Any Anthropic model id. |
| `temperature` | `float` | `0.7` | Sampling temperature. |
| `max_tokens` | `int` | `4096` | Per-call completion cap. Tight values truncate the structured `<answer>` block; the parser tolerates open-but-unclosed tags. |
| `tools` | `list[Any]` | `[]` | `Tool` instances. Passed to the API only if non-empty (real API rejects `tools=None`). |

**Cheap-path example** (Haiku for cost-sensitive runs):

```python
AgentConfig(
    name="Cheap",
    role="Summarizer",
    instructions="...",
    model="claude-3-5-haiku-20241022",
    temperature=0.2,
    max_tokens=256,
)
```

---

## `SwarmConfig`

The swarm itself — N agents that answer concurrently.

```python
from claudeway import Swarm, SwarmConfig, AgentConfig, WeightedVote

swarm = Swarm(SwarmConfig(
    name="ArchReview",
    description="Architecture review panel",
    agents=[
        AgentConfig("StrongConsistency", "Distributed Systems Engineer", "..."),
        AgentConfig("Operations",        "SRE / Platform Lead",          "..."),
        AgentConfig("Pragmatist",        "Staff Engineer",               "..."),
    ],
), api_key=...)
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | `str` | (required) | Stamped on every receipt — `swarm_name` is inside the signed payload. |
| `description` | `str` | (required) | Human description. |
| `agents` | `list[AgentConfig]` | `[]` | Member agents. Run concurrently via `asyncio.gather`, not serially. |
| `topology` | `str` | `"hierarchical_mesh"` | Advisory hint. **Currently not enforced** — all agents run peer-to-peer. |
| `consensus_method` | `str` | `"weighted_vote"` | Back-compat hint resolved to a strategy **only if** you don't pass `consensus=` to `Swarm()`. Values: `"weighted_vote"` (default/unknown), `"debate"` or `"revise"` → `Debate`. |
| `max_task_tokens` | `int` | `100_000` | Declared but **not enforced** in the current code path. |

### `Swarm.__init__` keyword arguments

The constructor takes these on top of the config:

| Param | Default | Notes |
|---|---|---|
| `api_key` | `None` | Anthropic key. `None` falls through to the `anthropic` SDK's env lookup of `ANTHROPIC_API_KEY`. |
| `consensus` | `None` | `ConsensusStrategy` instance. **Overrides** `SwarmConfig.consensus_method` if both are set — pick one. |
| `on_event` | `None` | Async callback fired on `AgentCompleted` / `ConsensusResolved`. Errors swallowed (intentional — buggy observer shouldn't crash consensus). |

---

## Consensus strategies

### `WeightedVote` (default)

One round, N API calls. Picks the max-confidence response.

```python
from claudeway import WeightedVote
swarm = Swarm(config, consensus=WeightedVote())
```

No constructor parameters.

`disagreed=True` when agreement score `< 0.6` OR the winning response's confidence `< 0.6`.

### `Debate`

Two rounds (2N API calls). Round 2 shows peers' answers to each agent for revision. **Early-exit**: if round 1 already exceeds the agreement threshold, round 2 is skipped (cost-guarded).

```python
from claudeway import Debate
swarm = Swarm(config, consensus=Debate(agreement_threshold=0.8))
```

| Param | Default | Notes |
|---|---|---|
| `agreement_threshold` | `0.8` | Skip the revision round if round-1 agreement ≥ threshold. Lower = more conservative (more debates); higher = fewer revision rounds. |

**Known limit:** the agreement scorer (`_agreement_score` → `_normalize_answer`) is **surface-form only** — lowercase, collapse whitespace, strip trailing punctuation. Three semantically equivalent but differently worded answers will score ~0.33 and trigger a debate round. Tracked as TODO semantic-agreement.

---

## `CoordinatorConfig`

The Coordinator is hierarchical decomposition (vs. the Swarm's parallel consensus). Config is a subclass of `AgentConfig` with all defaults overridden.

```python
from claudeway import Coordinator, CoordinatorConfig
coord = Coordinator(CoordinatorConfig())
```

| Param | Default |
|---|---|
| `name` | `"Coordinator"` |
| `role` | `"Task Coordinator and Manager"` |
| `instructions` | Built-in decomposition prompt (~4 lines) |
| `model` | `"claude-3-5-sonnet-20241022"` |
| `temperature` | `0.7` |
| `max_tokens` | `4096` |

Override any of these by passing kwargs:

```python
Coordinator(CoordinatorConfig(
    model="claude-3-5-haiku-20241022",
    max_tokens=2048,
))
```

**Note:** `CoordinatorConfig` is **not** a `@dataclass` — it's a plain `__init__` calling `super().__init__`. The `tools` field from `AgentConfig` is not exposed and defaults to `[]`. See [Coordinator](coordinator.md) for the decomposition flow.

---

## `ConsensusReceipt`

The signed attestation. You usually construct it via `ConsensusReceipt.from_result(...)` rather than field-by-field.

```python
from claudeway import ConsensusReceipt, Ed25519Backend

receipt = ConsensusReceipt.from_result(result, swarm_name="ArchReview", task_id="q1")
Ed25519Backend().sign_receipt(receipt, private_key)
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `payload` | `dict` | (required) | Canonical consensus facts. Hashed for the signature. |
| `algorithm` | `str` | `""` | Set by the backend on signing (`"ed25519"`, `"mldsa65"`). |
| `public_key` | `str` | `""` | Hex verification key. |
| `signature` | `str` | `""` | Hex signature over `sha256(canonical_json(payload))`. |
| `payload_hash` | `str` | `""` | Hex sha256 of canonical payload. |
| `signed_at` | `str` | `""` | ISO 8601 UTC timestamp. |
| `metadata` | `dict` | `{}` | Free-form transport hints. **Not signed.** |

The `is_signed` property returns `True` iff `signature`, `public_key`, and `algorithm` are all truthy.

---

## Signature backends

Both implement the `SignatureBackend` ABC. **No constructor parameters.**

### `Ed25519Backend` (default)

```python
from claudeway import Ed25519Backend
backend = Ed25519Backend()
```

- `algorithm="ed25519"`, 64-byte signatures
- Uses `cryptography` (already a core dep) — no extras required

### `MLDSABackend` (post-quantum, opt-in)

```python
from claudeway.signing_pq import MLDSABackend
backend = MLDSABackend()
```

- `algorithm="mldsa65"` (FIPS 204, NIST level 3), ~3.3 KB signatures
- Pure-Python via `dilithium-py`
- Install: `pip install claudeway[pq]`
- Lazy-imported — raises a clear `ImportError` without the extra

### Common API

```python
priv, pub = backend.generate_keypair()         # → (hex, hex)
sig = backend.sign(message_bytes, priv)         # → hex
ok = backend.verify(message_bytes, sig, pub)    # → bool

# Receipt-scoped convenience:
backend.sign_receipt(receipt, priv)             # mutates receipt in place
ok = backend.verify_receipt(receipt)            # re-hashes payload to detect post-signing tampering
```

---

## MCP server CLI

Entry point: `claudeway.server:main`. Run as `claudeway-mcp`.

```bash
claudeway-mcp                        # stdio (Claude Code, Cursor)
claudeway-mcp --http                 # HTTP/SSE (remote agents, default port 8765)
claudeway-mcp --http --port 9000     # custom port
claudeway-mcp --http --host 0.0.0.0  # bind all interfaces
```

| Flag | Default | Notes |
|---|---|---|
| `--http` | off | Serve over HTTP/SSE (streamable-http transport) instead of stdio. |
| `--host` | `127.0.0.1` | HTTP bind host. |
| `--port` | `8765` | HTTP bind port. |

No auth flag. No TLS flag. No log-level flag. For remote deployments, put it behind an authenticated reverse proxy.

---

## Environment variables

Only two are read anywhere in `claudeway/`:

| Var | Used by | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | `server.py` (MCP server) | Passed to `Swarm(api_key=...)`. |
| `CLAUDEWAY_SIGNING_KEY` | `server.py` | Hex Ed25519 private key. If set, MCP signs every receipt; if unset, receipts ship unsigned. |

**Important:** `Swarm()` and `Agent()` do **not** read env vars themselves. `api_key=None` falls through to the `anthropic` SDK's own env lookup. For non-server use, pass the key explicitly.

---

## Optional extras

Base install pulls: `anthropic>=0.40.0`, `cryptography>=42.0.0`, `httpx>=0.26.0`, `pydantic>=2.5.0`. Python `>=3.11`. License MIT.

| Extra | Pulls | Use when |
|---|---|---|
| `mcp` | `mcp>=1.0.0` | Running `claudeway-mcp`. |
| `nostr` | `coincurve>=20.0.0` | Signing/publishing Nostr events (Buzz interop). Prebuilt wheels for CPython 3.11–3.13. |
| `pq` | `dilithium-py>=1.4.0` | Post-quantum ML-DSA-65 signatures. |
| `langgraph` | `langgraph>=0.2.0`, `langchain-core>=0.3.0` | LangGraph adapter. |
| `maf` | `agent-framework-core>=1.0.0` | Microsoft Agent Framework adapter. |
| `crewai` | `crewai>=1.0.0` | CrewAI adapter. |
| `runner` | `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `python-multipart` | FastAPI control plane + dashboard backend (single-tenant runner). |
| `persist` | `sqlalchemy>=2.0.25`, `aiosqlite>=0.20.0` | Persist swarms/runs/receipts to SQLite. |
| `benchmark` | `crewai>=1.0.0` | Killer-demo harness. `litellm` optional for cost tracking (Windows-incompatible). |
| `dev` | `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `build` | Local development. |
| `docs` | `mkdocs`, `mkdocs-material`, `mkdocstrings[python]` | Building this docs site. |

Install multiple: `pip install claudeway[mcp,nostr,pq]`.

---

## Gotchas

- **Strategy precedence.** `Swarm(consensus=X)` overrides `SwarmConfig.consensus_method`. Setting both is a footgun — pick one.
- **`max_task_tokens` is declared but not enforced.** The field exists on `SwarmConfig`; no code path reads it. Don't rely on it for cost-guarding yet.
- **`topology` is advisory only.** No code branches on it. Reserved for future routing logic.
- **Agreement scoring is syntactic, not semantic.** Surface-form mismatch triggers a debate round even when answers are semantically equivalent.
- **Observer errors are swallowed.** A buggy `on_event` callback won't surface as a consensus failure (by design — keeps the swarm resilient). Log aggressively inside your callback if you need visibility.
- **`ANTHROPIC_API_KEY` isn't read by `Swarm`/`Agent`.** Only the MCP server reads it. SDK callers must pass `api_key=...` explicitly or rely on the `anthropic` SDK's env-var fallback.
