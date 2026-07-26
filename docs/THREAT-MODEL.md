# Claudeway — Threat Model

What the signed receipts protect, what they don't, and what an acquirer
should add. `tests/test_adversarial.py` proves each guarantee.

## The asset

The **consensus receipt**: a signed, tamper-evident attestation of what a
swarm agreed on and where it disagreed. If receipts can be forged or
silently rewritten, the layer has no point. Everything else is plumbing
whose security reduces to: does the receipt hold up?

## Adversary classes

**Malicious agent.** One agent lies confidently. Claudeway can't tell a
confident lie from a confident truth. It records every response verbatim
in the signed payload, so disagreement is visible to any verifier, not
hidden behind one confident answer.

**Compromised key holder.** Steals the Ed25519 key a node signs with.
Can forge new receipts under that key. Cannot forge receipts under other
keys, and cannot rewrite past receipts published elsewhere.

**Relay operator.** A Nostr relay or intermediary mutates a receipt in
transit, refuses delivery, or replays an old event as new. Tampering
invalidates the Nostr signature (rejected by every conformant relay and
by `nak verify`); replays fail because `task_id` is inside the signed
payload.

**Network MITM.** Same surface, plus "swap the pubkey to claim someone
else signed this." The signature binds to the canonical payload and
recorded public key; swapping either fails verification.

## What Claudeway guarantees

Proven by `tests/test_adversarial.py`:

- Mutating payload, signature, public key, or payload hash — any of the
  four signed surfaces — invalidates verification.
- A receipt from task-A does not verify as task-B's result (`task_id`
  and `swarm` are inside the signed payload).
- A stolen signing key cannot forge or invalidate receipts signed by
  other keys.
- When a majority of agents lie, the receipt still records every
  response — poisoning is visible, not laundered.
- Canonical JSON is actually canonical: payloads differing only in key
  order or whitespace hash identically; semantically different payloads
  hash differently.
- Nostr events with tampered content or signatures fail `nak verify`.

## What Claudeway does NOT guarantee

The seams an acquirer closes:

- **Agent identity is not verified.** Claudeway signs the output, not the
  agents. A swarm claiming "three independent reviewers" could be one
  process in three hats.
- **Agent correctness is not verified.** A confident wrong answer is
  recorded as confidently as a confident right one. The receipt attests
  *what was said*, not *what is true*.
- **The signing key is a long-lived secret.** If it leaks, every receipt
  signed by it becomes forgeable. No rotation, revocation, or forward
  secrecy.
- **Neither Ed25519 nor BIP-340 is post-quantum.** The backend is
  swappable so ML-DSA can drop in later; it doesn't ship today.
- **Relays can drop or reorder events.** Claudeway signs; delivery is
  not its problem.

## Recommended mitigations (out of scope here)

- Bind agent identities to verifiable credentials (DID/W3C VC); include
  their pubkeys in the signed payload.
- Add a key-rotation and revocation registry; version receipts by epoch.
- Track an ML-DSA backend so high-stakes receipts can demand
  post-quantum signatures when the standard matures.
- Require m-of-n signer receipts for high-stakes swarms, so no single
  key compromise undoes the attestation.
