---
title: Changelog
description: All notable changes to Claudeway. Follows Keep a Changelog; dates are ISO 8601.
---

# Changelog

All notable changes to Claudeway. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Dates are ISO 8601 (UTC).

## [Unreleased]

_No changes yet._

## [0.3.0] — 2026-07-25

The "everyone has agents, nobody has agreement" release. Claudeway ships as
the coordination layer that LangGraph, CrewAI, Microsoft Agent Framework,
and Buzzrooms all lack, with post-quantum-ready signatures and a reproducible
benchmark showing Claudeway beats both single Claude and CrewAI on hard
questions.

### Added
- **LangGraph adapter** (`claudeway.adapters.langgraph`): drop Claudeway
  consensus into a `StateGraph` as a single node. Two entry points —
  `make_consensus_node(swarm)` and `build_consensus_graph(swarm)`. Lazy
  import; install with `pip install claudeway[langgraph]`.
- **Microsoft Agent Framework adapter** (`claudeway.adapters.maf`):
  Claudeway as a MAF workflow + agent. MAF is Microsoft's unified successor
  to AutoGen + Semantic Kernel. Install with `pip install claudeway[maf]`.
- **CrewAI adapter** (`claudeway.adapters.crewai`): Claudeway consensus as
  a `@tool` and as a Flow. Inverts the killer demo — a CrewAI crew can call
  Claudeway for agreement. Install with `pip install claudeway[crewai]`.
- **Post-quantum signature backend** (`claudeway.signing_pq.MLDSABackend`):
  ML-DSA-65 / FIPS 204 signatures. Same receipt, same canonical payload
  hash — swap in at the `SignatureBackend` ABC. Pure-Python (`dilithium-py`),
  installs everywhere with no native build tools. Install with
  `pip install claudeway[pq]`.
- **Consensus transparency log** (`claudeway.transparency`): RFC 6962-style
  append-only log of consensus results, anchored to Nostr on a cadence.
  Tamper-evident beyond the per-receipt signature.
- **Streaming consensus events**: `OnEvent` callback hook surfaces
  `AgentCompleted` and `ConsensusResolved` events as they happen. Observable
  from any adapter (MAF, LangGraph, custom host).
- **Adversarial security test suite** (`tests/test_adversarial.py`): 20
  tests across 7 attack classes — signature forgery, receipt tampering,
  transport malleability, key reuse, replay, downgrade, and timestamp
  manipulation. Documented in `docs/THREAT-MODEL.md`.
- **Threat model** (`docs/THREAT-MODEL.md`): explicit attacker assumptions,
  what the signatures defend against, what they don't.
- **Docs site** (jordannewell.github.io/claudeway): mkdocs-material +
  mkdocstrings API reference. Auto-builds on push to `main` via the
  `docs.yml` workflow.
- **Community policies**: `SECURITY.md` (private vuln disclosure + SLA),
  `CONTRIBUTING.md` (branch model, commit rules, test commands),
  `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), issue templates.
- **Killer benchmark** (`examples/killer_demo.py`): same hard question →
  single Claude vs CrewAI vs Claudeway, blind LLM-judge scoring. Claudeway
  scores 18/20 (range 17–19) vs CrewAI 13/20 vs single Claude 11/20.
  Mann-Whitney U for non-parametric significance.

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

[Unreleased]: https://github.com/JordanNewell/claudeway/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.3.0
[0.2.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.2.0
[0.1.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.1.0
