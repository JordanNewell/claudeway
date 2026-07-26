---
title: Changelog
description: All notable changes to Claudeway. Follows Keep a Changelog; dates are ISO 8601.
---

# Changelog

All notable changes to Claudeway. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Dates are ISO 8601 (UTC).

## [Unreleased]

### Added
- **LangGraph adapter** (`claudeway.adapters.langgraph`): drop Claudeway
  consensus into a `StateGraph` as a single node. Two entry points —
  `make_consensus_node(swarm)` and `build_consensus_graph(swarm)`. Lazy
  import; install with `pip install claudeway[langgraph]`.
- **Killer benchmark** (`examples/killer_demo.py`): same hard question →
  single Claude vs CrewAI vs Claudeway, blind LLM-judge scoring. Results in
  `examples/killer_demo_results.md`. Claudeway scores +7/20 vs single Claude
  on average across 3 runs.

### Fixed
- **Stable signing key** in adapters: the LangGraph/CrewAI/MAF adapters now
  reuse a stable Ed25519 key across runs instead of regenerating per call,
  so signatures verify across runs and receipts are diffable.
- **Tolerant structured-output parser**: `<answer>` now carries the full
  response, parser falls back to "everything after `<answer>`" when small
  models truncate before `</answer>`. Latent `ConsensusResult.to_dict()`
  crash on dict-form responses fixed.
- **Substantive `<answer>` contract**: prompt explicitly requires the full
  multi-paragraph analysis inside `<answer>`, not a one-word verdict.
- **`Agent.think` no longer passes `tools=None`** as a kwarg (Anthropic SDK
  rejects it; previously suppressed when no tools were registered).
- **`asyncio.run_coroutine_threadsafe` self-deadlock** in adapter
  async→sync bridges: replaced with a fresh daemon worker thread + own loop.
  Works whether the caller is sync, async, or already in a thread.
- **Dropped dead `secp256k1` fallback** in `transports._nostr_sign`. The
  path called a `lib.schnorr_sign` API that never existed in coincurve;
  coincurve ships prebuilt wheels on all targets, so the CFFI fallback was
  dead complexity.
- **`[nostr]` extra mismatch** in `pyproject.toml`: was `pynostr`, code
  imports `coincurve`. Fixed.

### Changed
- README rewritten around the killer demo and LangGraph adapter.

## [0.2.0] — 2026-07-25

### Added
- **Verifiable multi-agent consensus for Claude** — initial public release.
- **Real consensus** — `WeightedVote` (cheap, default) and `Debate`
  (revision round when agents disagree, cost-guarded early-exit).
- **Real decomposition** — `Coordinator` parses a JSON plan and runs
  specialists in dependency-respecting parallel order.
- **Concurrent execution** — N-agent swarms issue all Claude calls in
  parallel via `asyncio.gather`.
- **Ed25519 signed receipts** — `ConsensusReceipt`, `Ed25519Backend`,
  swappable `SignatureBackend` ABC (post-quantum-ready).
- **Three transports** — JSON receipt, W3C Verifiable Credential, Nostr
  NIP-78 event (`kind: 30078`).
- **MCP server** (`claudeway-mcp`): exposes `reach_consensus` and
  `verify_consensus` as MCP tools for any MCP-capable agent.
- **Buzz adapter** (Nostr transport): `to_nostr_event` produces spec-correct
  events. Verified under `nak` (reference Nostr CLI); end-to-end tested
  against `nak serve`. Demo at `examples/buzz_consensus_demo.py`.
- **Lean extras model** — base install is 4 dependencies. `[mcp]`, `[nostr]`,
  `[runner]`, `[persist]`, `[dev]` are opt-in.
- **CI** — matrix (Ubuntu + Windows) × Python 3.11/3.12/3.13, ruff, pytest,
  wheel build + contents verification.
- **LICENSE** (MIT, Jordan Newell 2026), README + QUICKSTART rewritten
  around the coordination wedge.

## [0.1.0] — 2026-07-24

### Added
- Initial pre-release platform implementation (Next.js dashboard, FastAPI
  runner scaffolding, port management). Superseded by the 0.2.0 rewrite
  around the SDK + consensus wedge. The dashboard and multi-tenant runner
  are deferred — see
  [`docs/DEPRECATION.md`](https://github.com/JordanNewell/claudeway/blob/main/docs/DEPRECATION.md).

[Unreleased]: https://github.com/JordanNewell/claudeway/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.2.0
[0.1.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.1.0
