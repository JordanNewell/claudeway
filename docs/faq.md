---
title: FAQ
description: Questions a careful developer asks before adopting Claudeway. Honest answers — including where the SDK is unfinished.
---

# FAQ

The questions a careful developer asks before adopting Claudeway. Honest answers — including where the SDK is unfinished.

---

## Does this work with non-Claude models?

**No.** Claudeway is Claude-specific (per the name). It wraps the Anthropic SDK directly. Adding other model families would require an abstraction layer over the model client; not on the roadmap.

You can swap between Claude model tiers (Haiku, Sonnet, Opus) per agent via `AgentConfig.model` — useful for cost tuning.

---

## Is this a blockchain? A crypto project?

**No.** Claudeway uses standard Ed25519 signatures and Nostr's pub/sub protocol for transport. There is no ledger, no consensus algorithm between nodes, no token, no chain.

The signatures make receipts tamper-evident. Nostr makes them globally publishable. That's the entire "crypto" surface — both are pre-blockchain cryptography from the 1990s (Ed25519) and 2020 (Nostr NIP-01).

---

## How is this different from ensemble methods?

Ensembles run N model calls and **average** the results into a single confident answer. Claudeway runs N specialist agents, **surfaces disagreement** explicitly, and signs the consensus *with the trace intact* — who said what, where they diverged, how the strategy resolved it.

The receipt includes per-agent responses and the disagreement score, not just the final answer. See the [ensemble comparison](https://jordannewell.github.io/claudeway-site/#not-ensemble) on the landing page.

---

## How is this different from LangGraph / CrewAI / Goose?

Those frameworks coordinate agents — they don't produce signed agreement. Claudeway is the **consensus primitive** those frameworks don't ship. Use them for orchestration; use Claudeway when the orchestration needs to land on a verifiable, signed answer.

Adapters exist for [LangGraph, CrewAI, MAF, and Nostr transport](adapters.md). Drop Claudeway in as one node / tool / Flow.

---

## What does it cost?

Rough numbers at Haiku/Sonnet pricing:

| Path | Setup | Cost per consensus |
|---|---|---|
| Cheap (WeightedVote · Haiku · 256 tok) | 3 agents, 1 round | ~$0.01 |
| Debate (Haiku · 1k tok) | 3 agents, 2 rounds | ~$0.30 |
| Premium (Debate · Sonnet · 2k tok) | 3 agents, 2 rounds | ~$1.50 |

100 questions/day at the debate path ≈ $90/month. Use it for what's worth it; skip it when single-model confidence is enough. See [Tradeoffs](https://jordannewell.github.io/claudeway-site/#tradeoffs) on the landing.

---

## How long does a consensus call take?

~4× slower than a single Claude call. The benchmark: 29.8s for a full Claudeway Debate vs 7.5s for single Claude (same model, same hard question). The 4× comes from the 2-round Debate path; WeightedVote (1 round, N agents in parallel) is essentially the same latency as a single call.

For interactive UX where 30 s is too long, use `WeightedVote` instead of `Debate`.

---

## What happens if Claudeway dies? Am I locked in?

**No.** Receipts are self-contained Ed25519 signatures over a canonical JSON payload. Verify them with `nak`, OpenSSL, or a 20-line Python script — no Claudeway runtime required.

The SDK is MIT-licensed and will stay MIT. No BSL rug, no SSPL switch, no Open Core carve-out. If a hosted tier ships later, the SDK stays MIT.

---

## What's the security story?

- 17 adversarial tests across 7 attack classes (signature/payload/pubkey/hash tampering; replay; task substitution; single-key compromise; swarm poisoning; canonical-JSON equivocation; Nostr transport tampering).
- No third-party audit yet. The threat model is published at [THREAT-MODEL.md](THREAT-MODEL.md) — read it before relying on this for compliance.
- Honest "defends / doesn't defend" split: Claudeway proves receipt integrity, not agent identity (three "specialists" could be one process in three hats) or agent correctness (confident lies are recorded as confidently as confident truths).

---

## What doesn't Claudeway defend against?

- **Agent identity.** Three "specialists" could be one process in three hats.
- **Agent correctness.** Confident wrong answers are recorded as confidently as confident right ones.
- **Signing-key rotation / revocation / forward secrecy.** Not implemented yet.
- **Post-quantum attacks on default Ed25519/BIP-340.** Classical cryptography. The ML-DSA-65 backend ships (`pip install claudeway[pq]`) for forward-looking attestations.
- **Nostr relay delivery / ordering.** Relays can drop or reorder events. The signature defends integrity, not delivery.

---

## Is there a hosted/managed version?

**Not yet.** Multi-tenancy, billing, Stripe, template marketplace are explicitly **deferred** until paying demand appears (the "Curtis lesson" — don't build before there's demand). See [DEPRECATION.md](https://github.com/JordanNewell/claudeway/blob/main/docs/DEPRECATION.md) for the rationale.

A single-tenant runner (FastAPI + SQLite + dashboard, `docker compose up`) is on the roadmap.

---

## Is it production-ready?

**v0.3.x — pre-1.0.** Public API may shift. 1.0 ships when the signature surface is locked — at that point, canonical payload, receipt shape, and verifier interface freeze.

Currently 164 tests passing, 97% on critical-path modules (`signing`, `transports`, `transparency`, `consensus`). The MCP server and tools layer are at 0% coverage.

---

## How do I cite this?

```
Claudeway — Verifiable multi-agent consensus for Claude.
Jordan Newell, 2026-. https://github.com/JordanNewell/claudeway
```

Or just link to the repo or the docs.
