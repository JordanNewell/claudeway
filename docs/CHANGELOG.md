---
title: Changelog
description: All notable changes to Tractum. Follows Keep a Changelog; dates are ISO 8601.
---

# Changelog

All notable changes to Tractum (formerly claudeway). Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Dates are ISO 8601 (UTC).

## [Unreleased]

_No changes yet._

## [0.5.0] — 2026-10-17

Feature release — **.curt linkage, self-verifying MCP receipts, and the
claudeway → tractum rename.**

### Added
- **.curt linkage** (`tractum.curt_link`): a quorum receipt is the DECISION;
  the .curt transcript(s) the consensus was computed from are the EVIDENCE.
  `build_curt_transcript` renders a `ConsensusResult` as a conforming .curt
  v1 document (per-message agent provenance via the `agent-context`
  extension), `link_receipt` embeds transcript refs ({id, sha256}) INSIDE
  the signed payload — so the aggregate signature covers the linkage —
  `emit_curt_decision` emits receipt + evidence as one .curt artifact (the
  `consensus-receipt` extension), and `verify_curt_link` verifies the whole
  chain through the existing crypto paths. Unlinked payloads stay
  byte-identical to the 0.4.0 wire format.
- **MCP `reach_consensus` always signs.** Without a configured operator
  key the server now signs each receipt with a fresh **ephemeral**
  keypair instead of returning an unsigned receipt that `verify_consensus`
  would reject. The ephemeral public key rides in the response
  (`public_key`; `metadata.operator_key: "ephemeral"` marks the mode).
- **`TRACTUM_REQUIRE_PINNED_KEY=1`** for deployments that must never ship
  an ephemeral-signed receipt: without a configured `TRACTUM_SIGNING_KEY`
  the call fails loudly with a clear error instead of signing with a
  throwaway key.
- **Dry-run mode.** `TRACTUM_MCP_DRY_RUN=1` or a per-call
  `"dry_run": true` runs deterministic offline stub agents — per-agent
  keypairs, real statement signatures, zero API calls. The receipt
  self-identifies (swarm `mcp-consensus-dry-run`, stub answers, metadata
  `dry_run`) so it can never pass as a live decision.
- **MCP `verify_consensus` accepts `expected_agent_pubkeys`** and pins
  each agent's statement to a known key via
  `verify_receipt_detailed` (0.4.0's docs promised this; the tool now
  actually honors it).

### Fixed
- **MCP docs matched to the code** (`docs/mcp-server.md`): specialists
  take `instructions` (not `perspective`); removed the phantom
  `"sign": true` parameter; removed the nonexistent
  `CLAUDEWAY_MCP_TOKEN` bearer-auth section (the HTTP transport has no
  built-in auth — now documented as such); documented the real env vars.
- **.curt message-id collision**: message ids used only the first 12
  chars of the content-addressed conversation id, so two transcripts whose
  ids shared leading digest chars (~1-in-256) collided when merged into a
  decision artifact and `emit_curt_decision` silently dropped evidence.
  Ids now embed the full conversation id (regression test added).

### Changed
- **Renamed: claudeway → tractum.** The Python package, module, and CLI
  are now `tractum`.
  - Imports: `from claudeway import ...` → `from tractum import ...`;
    module directory `claudeway/` → `tractum/`; console script
    `claudeway-mcp` → `tractum-mcp`.
  - Env vars: `CLAUDEWAY_SIGNING_KEY` → `TRACTUM_SIGNING_KEY`,
    `CLAUDEWAY_TEST_RELAY` → `TRACTUM_TEST_RELAY`,
    `CLAUDEWAY_TEST_LANGGRAPH` → `TRACTUM_TEST_LANGGRAPH`,
    `CLAUDEWAY_RUN_LIVE` → `TRACTUM_RUN_LIVE`, and
    `CLAUDEWAY_DEMO_RELAY` → `TRACTUM_DEMO_RELAY`.
  - PyPI: the package publishes as **`tractum`** (the `claudeway` name
    never shipped to PyPI; 0.2.0–0.4.0 were GitHub-only).
  - **Wire-format type tags are UNCHANGED for backward compatibility:**
    receipts still carry `claudeway.consensus.v1` /
    `claudeway.consensus.v2` / `claudeway.agent-statement.v1` payload
    types and the `claudeway.receipt.v1` envelope type — all shipped
    publicly since v0.2.0/0.3.2, and the verifier accepts them forever.
    The W3C VC context URL is likewise unchanged. Nostr d-tags and the
    client tag ARE renamed (`claudeway-consensus` → `tractum-consensus`,
    `claudeway-transparency` → `tractum-transparency`, client
    `claudeway` → `tractum`): these are self-asserted metadata on
    self-signed events, not verification inputs, so old events stay valid
    and old relays keep working. Existing receipts and .curt linkages
    verify without migration.
  - Newly written .curt transcripts use `generator: "tractum"` and
    `tractum-`-prefixed content-addressed conversation ids; existing ids
    are opaque and remain valid (verification is hash-based).
  - License unchanged: BUSL-1.1, Licensor Jordan Newell.

### Migration (from claudeway 0.4.x)

```bash
pip uninstall claudeway   # if installed from the repo under the old name
pip install tractum       # PyPI at launch; until then install from the repo
```

```python
# old                          # new
from claudeway import Swarm    from tractum import Swarm
```

| Old | New |
| --- | --- |
| `from claudeway import ...` | `from tractum import ...` |
| `claudeway-mcp` | `tractum-mcp` |
| `CLAUDEWAY_SIGNING_KEY` | `TRACTUM_SIGNING_KEY` |
| `CLAUDEWAY_TEST_RELAY` | `TRACTUM_TEST_RELAY` |
| `CLAUDEWAY_TEST_LANGGRAPH` | `TRACTUM_TEST_LANGGRAPH` |
| `CLAUDEWAY_RUN_LIVE` | `TRACTUM_RUN_LIVE` |
| `CLAUDEWAY_DEMO_RELAY` | `TRACTUM_DEMO_RELAY` |
| `claudeway.consensus.*` / `claudeway.agent-statement.v1` / `claudeway.receipt.v1` type tags | **unchanged** — backward-compat wire format |

## [0.4.0] — 2026-10-01

Feature release — **per-agent signed statements and k-of-n quorum receipts.**
The receipt stops being one operator's claim about what the agents said and
becomes a countable multi-sig: every agent signs its own stance, and anyone
can verify the signatures individually.

### Added
- **Per-agent signed statements.** Every agent in a `Swarm` now gets a
  signing keypair (pinned via `AgentConfig.signing_key`, otherwise an
  ephemeral key is provisioned per swarm) and signs a
  `claudeway.agent-statement.v1` statement over its stance — answer,
  confidence, model, role, task, round. Statements ride on
  `AgentResponse.statement` and survive dict round-trips through
  `Task.result`.
- **v2 receipt payload (`claudeway.consensus.v2`).** When statements are
  present, `ConsensusReceipt.from_result` emits a payload carrying the
  statements plus a `quorum` threshold k (default: unanimous). The
  operator's aggregate signature covers the agent signatures too. v1
  receipts are produced unchanged when no statements exist — the verifier
  handles both forever.
- **`verify_receipt_detailed(receipt, expected_operator_pubkey="",
  expected_agent_pubkeys={})`** — full verification report: aggregate
  signature, per-statement signature/hash checks, statement↔response
  cross-checks (`response-mismatch:answer`/`confidence`), cross-task replay
  detection (`task-id-mismatch`), operator and per-agent key pinning
  (`key-mismatch`), and the quorum count. Returns a `ReceiptVerification`
  with per-statement reasons.
- **Statement helpers** — `SignatureBackend.sign_statement` /
  `verify_statement` (implemented once on the ABC, inherited by Ed25519 and
  ML-DSA-65 backends; mixed-algorithm statements verify per statement),
  plus module-level `sign_statement` / `verify_statement` /
  `statement_hash`.
- **MCP `verify_consensus` upgrade** — the tool now accepts optional
  `expected_operator_pubkey` / `expected_agent_pubkeys` and returns the
  full statement-by-statement verdict, not just a boolean.

### Security
- New adversarial tests for the statement attack surface: operator
  fabrication of statements under fresh keys (caught by per-agent pinning),
  statement tampering inside a signed receipt (aggregate hash guard),
  cross-task statement replay (`task-id-mismatch`), statement/response
  desync (`response-mismatch`), and stolen-agent-key isolation.
- Honest threat-model note: a signature proves self-consistency, not key
  custody. Without per-agent pinning, a malicious operator can mint
  self-consistent statements under fresh keys — pinning is what makes
  fabrication detectable. See `docs/THREAT-MODEL.md`.

### Compatibility
- v1 receipts verify exactly as before; `verify_receipt` semantics are
  unchanged. Responses without statements keep their v1 dict shape
  byte-for-byte, so existing payload hashes and transparency-log anchors
  are unaffected.

## [0.3.2] — 2026-07-26

Maintenance release — CI/docs only, no package behavior change.

### Changed
- **Publish workflow uses OIDC trusted publishing (no API tokens).** PyPI
  trusted-publisher configuration corrected; the GitHub Actions workflow
  now mints a short-lived OIDC token at publish time. Removes the need
  for any long-lived `PYPI_API_TOKEN` secret on the repo.
- **README ships with a canonical Open Graph image and banner.** Social
  previews (Twitter/X, LinkedIn, Slack, Discord) now render the Claudeway
  card instead of a blank tile.

## [0.3.1] — 2026-07-26

Hotfix release. Unblocks `pip install claudeway[benchmark]` on Windows.

### Fixed
- **`[benchmark]` extra no longer pulls `litellm`**. The `litellm>=1.18` dep
  transitively requires a Rust build toolchain that fails on Windows. The
  killer demo (`examples/killer_demo.py`) now imports litellm lazily with a
  try/except — token-cost tracking is degraded on Windows when litellm is
  absent (it was already unreliable on Windows + litellm 1.18+ per the
  inline comment), but the demo itself runs. Full token tracking on
  Linux/macOS is restored by `pip install litellm` separately. The Docker
  compose appliance (which is Linux) installs litellm in its Dockerfile.

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

[Unreleased]: https://github.com/JordanNewell/claudeway/compare/v0.4.0...HEAD
[0.5.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.5.0
[0.4.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.4.0
[0.3.2]: https://github.com/JordanNewell/claudeway/releases/tag/v0.3.2
[0.3.1]: https://github.com/JordanNewell/claudeway/releases/tag/v0.3.1
[0.3.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.3.0
[0.2.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.2.0
[0.1.0]: https://github.com/JordanNewell/claudeway/releases/tag/v0.1.0
