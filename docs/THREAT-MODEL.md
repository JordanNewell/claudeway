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
in the signed payload — and since v0.4.0, each agent signs its own stance
— so disagreement and forgery are visible to any verifier, not hidden
behind one confident answer.

**Malicious operator.** The party running the swarm fabricates the whole
thing: no agents ran, but the receipt says three specialists agreed. This
is the adversary the v0.4.0 k-of-n design addresses. Statement signatures
are cryptographically self-consistent under ANY key, so a determined
operator can mint statements under fresh keys — but a verifier that pins
the agent pubkeys it knows (`expected_agent_pubkeys` in
`verify_receipt_detailed`) rejects every one of them (`key-mismatch`).
Pinning is what turns "the operator says the agents signed" into "these
are the agents' keys, and here are their signatures."

**Compromised key holder.** Steals the Ed25519 key a node signs with.
Can forge new receipts — and, since v0.4.0, new statements — under that
key only. Pinning stops a stolen agent-key from signing as a *different*
agent; the compromise does not propagate. Cannot forge receipts or
statements under other keys, and cannot rewrite past receipts published
elsewhere.

**Relay operator.** A Nostr relay or intermediary mutates a receipt in
transit, refuses delivery, or replays an old event as new. Tampering
invalidates the Nostr signature (rejected by every conformant relay and
by `nak verify`); replays fail because `task_id` is inside the signed
payload — and statements are individually pinned to their task
(`task-id-mismatch`).

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

Since v0.4.0 (per-agent statements, k-of-n receipts):

- Every agent statement is individually verifiable: content hash,
  signature, and consistency with the response it claims to attest.
  Editing an answer inside a signed statement trips both the aggregate
  hash guard and the statement hash.
- A statement from task-A cannot be recycled inside a task-B receipt
  (`task-id-mismatch`), and a statement cannot be re-pointed at a
  different answer than the one its response records
  (`response-mismatch:answer`).
- The quorum threshold k is part of the signed payload — downgrading it
  post-hoc invalidates the aggregate signature.
- With per-agent key pinning, an operator (or attacker) minting
  statements under fresh keys is caught on every statement
  (`key-mismatch`), and the quorum honestly reports unmet.
- One compromised agent key forges only that agent's statements; with
  pinning it cannot sign as any other agent.

## What Claudeway does NOT guarantee

The seams an acquirer closes:

- **Signer independence is a deployment property, not a crypto one.**
  v0.4.0 gives every agent its own keypair, but in a single-process swarm
  the operator provisions (and therefore holds) all of them. "Three
  independent signers" becomes cryptographically real when agents run in
  separate trust domains and bring their own keys — the receipt format
  already supports it; cross-host signing is the follow-through.
- **Signatures prove self-consistency, not custody.** A statement signed
  with agent A's key proves A's key signed it — not that A (or anyone
  honest) currently holds it. Without `expected_agent_pubkeys` pinning, a
  malicious operator can mint self-consistent statements under fresh
  keys and naive verification will not catch it. Pin the keys you know.
- **Agent correctness is not verified.** A confident wrong answer is
  recorded — and now individually signed — as confidently as a
  confident right one. The receipt attests *what was said*, not *what is
  true*.
- **The signing keys are long-lived secrets.** If one leaks, everything
  signed by it becomes forgeable. No rotation, revocation, or forward
  secrecy.
- **Ed25519 and BIP-340 are not post-quantum.** The default Ed25519
  backend and the BIP-340 Schnorr signatures used for Nostr transport
  are classical. An **ML-DSA-65 (FIPS 204)** backend ships as of v0.3.0
  (`claudeway.signing_pq.MLDSABackend`, pure-Python via `dilithium-py`,
  install with `pip install claudeway[pq]`) for attestations that must
  stay verifiable across the transition to cryptographically relevant
  quantum hardware. The same receipt, same canonical payload hash —
  swap in at the `SignatureBackend` ABC. Statements can be signed with a
  different (mix of) backend(s) than the aggregate; the verifier
  dispatches per statement algorithm.
- **Relays can drop or reorder events.** Claudeway signs; delivery is
  not its problem.

## Recommended mitigations (out of scope here)

- Bind agent identities to verifiable credentials (DID/W3C VC); include
  their pubkeys in the signed payload.
- Add a key-rotation and revocation registry; version receipts by epoch.
- Use the ML-DSA-65 backend (ships in v0.3.0) for high-stakes receipts
  that must remain verifiable under post-quantum threat models.
- Give each agent its own key in its own trust domain (cross-host agent
  signing) so the k-of-n property reflects independent custodians, not
  one operator's keyring.
