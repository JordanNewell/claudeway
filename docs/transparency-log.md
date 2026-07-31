---
title: Transparency log
description: RFC 6962-style append-only Merkle log of consensus receipts, anchored to Nostr on a cadence. Proves the set of decisions Claudeway made, not just each receipt's integrity.
---

# Transparency log

An **append-only Merkle log of consensus receipts**, anchored to Nostr. Certificate Transparency (RFC 6962) adapted for agent consensus — receipts-as-leaves, Nostr-anchored on day 1, Bitcoin anchoring via OpenTimestamps (NIP-3) planned for day 2.

---

## Why it exists

Per-receipt Ed25519 signatures prove **integrity** — the receipt wasn't altered. They don't prove **completeness** — nothing prevents Claudeway from quietly hiding, removing, or re-issuing a receipt.

The transparency log closes that gap on a separate trust axis: it commits to *the set of decisions that exist*. Once a log root is published, a receipt that disappears leaves a detectable gap; a receipt that was secretly altered invalidates every proof that referenced it.

---

## The math (lightly)

The log is a binary Merkle tree over leaf hashes, following [RFC 6962 §2.1](https://datatracker.ietf.org/doc/html/rfc6962#section-2.1) verbatim:

- **Leaf hash:** `SHA-256(0x00 || canonical_payload)` — the payload is the exact bytes the receipt signature covers, so log and signature bind to the same data.
- **Internal node:** `SHA-256(0x01 || L || R)`.
- The `0x00` / `0x01` domain separators prevent second-preimage attacks.
- **Root:** the hash of the full tree; an empty log has root `SHA-256(b"")` so a fresh log has a publishable root before any receipts.

**Inclusion proof** (`InclusionProof`): a list of sibling hashes from a leaf up to the root, plus the leaf index and the tree size at issue time. `verify_inclusion` walks the path, hashing the leaf with each sibling in RFC 6962's left/right order, and compares the result to the expected root. Returns `True` iff the proof chains the receipt's leaf to that root — **no `TransparencyLog` instance required**.

The "tree at size N" construction keeps proofs stable: a proof issued at size N still verifies at size N+k against the size-N root.

Cross-validated byte-for-byte against Google's reference `ct/crypto/merkle.py` across tree sizes 1–1000 (`tests/test_transparency.py::test_root_matches_google_reference`).

---

## Nostr anchoring

A `LogAnchor` (tree_size + root + timestamp) is rendered as a **NIP-78 kind-30078 event** via `claudeway.transports.to_log_anchor_event`, scoped by the d-tag `claudeway-transparency` and a `name` tag carrying the logical log identity.

Publishing anchors on a cadence makes the log's history globally visible: third parties watching the relay see every root Claudeway commits, and a missing or replaced anchor is detectable. Day 1 relies on Nostr's append-only-on-relay semantics plus operator reputation; day-2 consistency proofs and Bitcoin anchoring turn "tamper-evident" into "tamper-proof."

---

## API surface

```python
from claudeway.transparency import (
    TransparencyLog, InclusionProof, LogAnchor,
    leaf_hash, node_hash,
)
```

| Symbol | Signature | Notes |
|---|---|---|
| `TransparencyLog(name="claudeway")` | constructor | One logical log per Nostr key. In-memory. |
| `log.append(receipt)` | `-> int` | Appends the receipt's leaf hash; returns the 0-based leaf index. Only mutator. |
| `log.size` | `@property -> int` | Current leaf count. |
| `log.root` | `@property -> bytes` | 32-byte Merkle root; `SHA-256(b"")` when empty. |
| `log.inclusion_proof(leaf_index)` | `-> InclusionProof` | Raises `IndexError` if out of range. |
| `TransparencyLog.verify_inclusion(receipt, proof, expected_root)` | `@staticmethod -> bool` | Standalone — no log instance needed. |
| `LogAnchor(tree_size, root, published_at, nostr_event_id=None)` | dataclass | `.to_dict()` produces the wire payload. |
| `to_log_anchor_event(anchor, private_key_hex, log_name="", created_at=None)` | transport helper | Returns a `NostrEvent` (kind 30078). |

`InclusionProof` fields: `leaf_index: int`, `tree_size: int`, `audit_path: list[bytes]`.

---

## Example

```python
from claudeway.transparency import TransparencyLog

log = TransparencyLog(name="claudeway-canonical")
indices = [log.append(r) for r in (r1, r2, r3)]   # -> [0, 1, 2]
root = log.root                                    # publish this as a Nostr anchor

proof = log.inclusion_proof(1)                     # proof for r2
assert TransparencyLog.verify_inclusion(r2, proof, root) is True

# Tamper with r2's answer -> leaf hash changes -> proof no longer chains to root
tampered = rebuild_receipt_with_answer("use mongodb instead")
assert TransparencyLog.verify_inclusion(tampered, proof, root) is False
```

---

## Use cases

- **Compliance and regulatory audits** — prove a decision was or wasn't made.
- **Dispute resolution** — independent record of consensus outcomes.
- **AI-governance accountability** — multiple parties need to verify the same set of AI decisions.
- **Multi-party workflows** where participants need an independent record.
- Any setting where "trust the operator to show you the right receipts" is insufficient.

---

## Persistence

**In-memory only.** No SQLAlchemy, sqlite, or file backend. The log holds leaf hashes (not payloads) in a `list[bytes]`; receipts are reproducible from their canonical payload.

Production deployments are expected to persist anchors via the Nostr event stream itself and rebuild the in-memory log by replaying receipts. A cached "lazy root" (RFC 6962 right-edge sub-trees) is explicitly out of scope for day 1.

---

## Composability with streaming events

Wire streaming events (see [Streaming events](streaming-events.md)) into the log: capture `consensus_receipt` events from your stream consumer, hydrate them as `ConsensusReceipt` objects, then `log.append(receipt)`. This builds the log automatically as consensus events arrive — no separate pipeline.
