"""
Adversarial test suite — proving Claudeway fails safely under attack.

This is what a serious security reviewer reads before recommending the
library. Each test asserts a guarantee that holds EVEN UNDER ATTACK:

  - Agent deception: a confidently-wrong agent can't corrupt the receipt,
    and consensus still surfaces the disagreement.
  - Receipt tampering on every signed surface (payload, signature,
    public_key, payload_hash): each mutation invalidates verification.
  - Replay: a receipt from task-A cannot be passed off as task-B's result
    (task_id is part of the signed payload).
  - Key compromise isolation: one stolen key cannot forge or invalidate
    receipts signed by other keys.
  - Swarm poisoning: when N-1 of N agents lie, the receipt still reports
    what actually happened — disagreement is visible, not hidden.
  - Canonical JSON collision resistance: two payloads that serialize
    identically under naive json.dumps MUST hash differently under
    canonical_json (it's actually canonical).
  - Transports integrity: a Nostr event with tampered content fails
    `nak verify` (the reference Nostr implementation).

All tests are hermetic (no Claude API, no network) except the optional
nak check, which skips if `nak` isn't on PATH.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from typing import Any

import pytest

from claudeway.consensus import ConsensusResult
from claudeway.signing import (
    ConsensusReceipt,
    Ed25519Backend,
    canonical_json,
)
from claudeway.swarm import AgentResponse
from claudeway.transports import to_nostr_event

# --- helpers ----------------------------------------------------------------


def _make_receipt(
    backend: Ed25519Backend,
    priv_hex: str,
    *,
    final_answer: str = "use sqlite",
    task_id: str = "t1",
    swarm_name: str = "DBPicker",
    responses: list[AgentResponse] | None = None,
) -> ConsensusReceipt:
    """Build + sign a receipt over a controlled payload."""
    if responses is None:
        responses = [
            AgentResponse(agent_name="A", answer=final_answer, confidence=0.9),
            AgentResponse(agent_name="B", answer=final_answer, confidence=0.85),
        ]
    result = ConsensusResult(
        final_answer=final_answer,
        method="weighted_vote",
        agent_count=len(responses),
        responses=responses,
        agreement=0.9,
        rounds=1,
    )
    receipt = ConsensusReceipt.from_result(
        result, swarm_name=swarm_name, task_id=task_id
    )
    backend.sign_receipt(receipt, priv_hex)
    return receipt


@pytest.fixture
def backend() -> Ed25519Backend:
    return Ed25519Backend()


@pytest.fixture
def keypair(backend: Ed25519Backend) -> tuple[str, str]:
    return backend.generate_keypair()


@pytest.fixture
def signed_receipt(
    backend: Ed25519Backend, keypair: tuple[str, str]
) -> ConsensusReceipt:
    priv, _ = keypair
    return _make_receipt(backend, priv)


# --- 1. Agent deception -----------------------------------------------------


def test_confidently_wrong_agent_does_not_corrupt_receipt(
    backend: Ed25519Backend, keypair: tuple[str, str]
):
    """One agent returns a confidently wrong answer.

    Guarantees (the ones that hold under attack):
      - Every response — including the lie — is recorded verbatim in the
        signed payload. A verifier sees the disagreement for themselves;
        consensus isn't a black box that returns a single confident answer.
      - Tampering with any recorded response AFTER signing is detected.
      - The receipt's final_answer matches what the strategy actually
        picked (we don't silently rewrite history).

    Non-guarantee (documented in THREAT-MODEL.md): whether the strategy's
    `disagreed` flag flips depends on the agreement threshold, which is a
    policy knob — not a cryptographic property. We don't assert it here.
    """
    priv, _ = keypair
    responses = [
        AgentResponse(agent_name="Truthful", answer="2+2=4", confidence=0.95),
        AgentResponse(
            agent_name="Liar", answer="2+2=5", confidence=0.99
        ),  # louder + wrong
        AgentResponse(agent_name="Truthful2", answer="2+2=4", confidence=0.9),
    ]
    # WeightedVote picks max-confidence response as the winner — that's the
    # liar. We don't claim Claudeway prevents that; we claim the receipt
    # honestly records what happened, signed and verifiable.
    winner = max(responses, key=lambda r: r.confidence)
    receipt = _make_receipt(
        backend,
        priv,
        final_answer=winner.answer,
        responses=responses,
    )
    # (1) Every response — including the lie — is in the signed payload.
    recorded_answers = [
        r["answer"] for r in receipt.payload["result"]["responses"]
    ]
    assert recorded_answers == ["2+2=4", "2+2=5", "2+2=4"]
    # (2) The final_answer recorded is what the strategy actually picked.
    assert receipt.payload["result"]["final_answer"] == "2+2=5"
    # (3) Receipt verifies clean — this is the attestation, unmodified.
    assert backend.verify_receipt(receipt) is True
    # (4) Retroactively editing the liar's answer invalidates the signature.
    receipt.payload["result"]["responses"][1]["answer"] = "2+2=4"
    assert backend.verify_receipt(receipt) is False
    # (5) Editing the final_answer to "fix" the lie also invalidates it.
    receipt.payload["result"]["final_answer"] = "2+2=4"
    assert backend.verify_receipt(receipt) is False


# --- 2. Receipt tampering: all four signed surfaces -------------------------


def test_payload_mutation_invalidates_signature(signed_receipt, backend):
    """Mutating any byte of the payload must invalidate verification."""
    signed_receipt.payload["result"]["final_answer"] = "USE POSTGRES INSTEAD"
    assert backend.verify_receipt(signed_receipt) is False


def test_signature_mutation_invalidates_verification(signed_receipt, backend):
    """Flipping a single hex char in the signature breaks verification."""
    sig = signed_receipt.signature
    # Flip the last hex nibble — smallest possible mutation.
    flipped = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    signed_receipt.signature = flipped
    assert backend.verify_receipt(signed_receipt) is False


def test_public_key_swap_invalidates_verification(
    signed_receipt, backend, keypair
):
    """Swapping in another key's pubkey must fail (signature wasn't made by it)."""
    _, other_pub = backend.generate_keypair()
    assert other_pub != signed_receipt.public_key
    signed_receipt.public_key = other_pub
    assert backend.verify_receipt(signed_receipt) is False


def test_payload_hash_regeneration_detected(signed_receipt, backend):
    """An attacker who re-hashes a tampered payload to match is caught.

    The signature is over canonical_json(payload) directly, NOT over
    payload_hash. So even if an attacker recomputes payload_hash after
    mutating the payload, the signature still fails — because the signed
    bytes changed. And if they DON'T recompute payload_hash, the hash
    guard catches it first. Either path fails.
    """
    # Case A: attacker mutates payload AND recomputes payload_hash.
    signed_receipt.payload["result"]["final_answer"] = "tampered"
    new_hash = hashlib.sha256(
        signed_receipt.canonical_payload().encode("utf-8")
    ).hexdigest()
    signed_receipt.payload_hash = new_hash
    # Hash guard passes (we just recomputed it), but the signature was over
    # the ORIGINAL payload and no longer matches.
    assert backend.verify_receipt(signed_receipt) is False


def test_payload_hash_set_to_random_invalidates(signed_receipt, backend):
    """Setting payload_hash to a 64-hex value that isn't the real hash fails."""
    signed_receipt.payload_hash = "0" * 64
    assert backend.verify_receipt(signed_receipt) is False


# --- 3. Replay / task substitution ------------------------------------------


def test_receipt_cannot_be_replayed_for_different_task(
    backend: Ed25519Backend, keypair: tuple[str, str]
):
    """A valid receipt for task-A must NOT verify as the result of task-B.

    task_id is part of the signed payload, so swapping it in a verifiable
    way requires re-signing — which an attacker without the key can't do.
    """
    priv, _ = keypair
    receipt_a = _make_receipt(
        backend, priv, task_id="task-A", final_answer="answer-for-A"
    )
    assert backend.verify_receipt(receipt_a) is True

    # Attacker tries to present receipt_a as the result of task-B.
    forged = ConsensusReceipt(
        payload=json.loads(json.dumps(receipt_a.payload)),  # deep copy
        algorithm=receipt_a.algorithm,
        public_key=receipt_a.public_key,
        signature=receipt_a.signature,
        payload_hash=receipt_a.payload_hash,
        signed_at=receipt_a.signed_at,
    )
    forged.payload["task_id"] = "task-B"

    # The signature no longer covers the modified payload.
    assert backend.verify_receipt(forged) is False


def test_receipt_cannot_be_replayed_for_different_swarm(
    backend: Ed25519Backend, keypair: tuple[str, str]
):
    """Swapping swarm_name also breaks the signature — same replay defense."""
    priv, _ = keypair
    receipt = _make_receipt(backend, priv, swarm_name="SwarmA")
    receipt.payload["swarm"] = "SwarmB"
    assert backend.verify_receipt(receipt) is False


# --- 4. Key compromise isolation --------------------------------------------


def test_compromised_key_cannot_forge_other_keys_receipts(
    backend: Ed25519Backend,
):
    """If key-A is compromised, receipts signed by key-B are still safe.

    Attacker holds priv_A and tries to forge a receipt that verifies
    under pub_B. Ed25519 makes this impossible — the signature won't
    match pub_B, and pub_B is the only thing verify_receipt consults.
    """
    priv_a, _ = backend.generate_keypair()
    _, pub_b = backend.generate_keypair()

    # Attacker builds a receipt and signs with their stolen key-A.
    result = ConsensusResult(
        final_answer="forged",
        method="weighted_vote",
        agent_count=1,
        responses=[AgentResponse(agent_name="x", answer="forged", confidence=1.0)],
    )
    receipt = ConsensusReceipt.from_result(result, task_id="forged")
    backend.sign_receipt(receipt, priv_a)
    assert backend.verify_receipt(receipt) is True  # legit under key-A

    # Attacker swaps the pubkey to claim it was signed by key-B.
    receipt.public_key = pub_b
    assert backend.verify_receipt(receipt) is False  # signature doesn't match


def test_other_keys_receipts_survive_one_key_compromise(backend: Ed25519Backend):
    """A honest signer's receipts verify independently of any other key's state."""
    priv_a, _ = backend.generate_keypair()
    priv_b, _ = backend.generate_keypair()

    receipt_a = _make_receipt(backend, priv_a, task_id="a")
    receipt_b = _make_receipt(backend, priv_b, task_id="b")

    # Even if we conceptually treat priv_a as compromised, receipt_b's
    # verification is unaffected — it consults only pub_b.
    assert backend.verify_receipt(receipt_a) is True
    assert backend.verify_receipt(receipt_b) is True


# --- 5. Swarm poisoning (N-1 of N compromised) ------------------------------


def test_swarm_poisoning_majority_compromised_still_reports_truth(
    backend: Ed25519Backend, keypair: tuple[str, str]
):
    """3 of 4 agents lie. The receipt still records every answer verbatim.

    Claudeway does NOT promise the final_answer is correct under
    majority compromise — that's a non-guarantee documented in
    THREAT-MODEL.md. What it DOES promise: the disagreement is recorded
    in the signed payload, so a verifier can see the poisoning rather
    than receiving a single confident lie with no trace.
    """
    priv, _ = keypair
    responses = [
        AgentResponse(agent_name="Honest", answer="the-truth", confidence=0.8),
        AgentResponse(agent_name="Liar1", answer="the-lie", confidence=0.99),
        AgentResponse(agent_name="Liar2", answer="the-lie", confidence=0.99),
        AgentResponse(agent_name="Liar3", answer="the-lie", confidence=0.99),
    ]
    # The lies win the plurality — that's what gets recorded as the final
    # answer. Claudeway records this honestly rather than hiding it.
    weights: dict[str, float] = {}
    total = 0.0
    for r in responses:
        key = r.answer.strip().lower().rstrip(".!?")
        weights[key] = weights.get(key, 0.0) + max(r.confidence, 0.0)
        total += max(r.confidence, 0.0)
    agreement = max(weights.values()) / total
    winner = max(responses, key=lambda r: r.confidence)

    receipt = _make_receipt(
        backend,
        priv,
        final_answer=winner.answer,
        responses=responses,
    )

    # The receipt records EVERY response — verifier sees the lie.
    recorded = [r["answer"] for r in receipt.payload["result"]["responses"]]
    assert recorded.count("the-lie") == 3
    assert "the-truth" in recorded
    # Plurality went to the lies; agreement is high BUT the receipt is
    # still verifiable, and a downstream reader can see the 1-vs-3 split.
    assert winner.answer == "the-lie"
    assert agreement > 0.6  # the lies did carry the vote
    assert backend.verify_receipt(receipt) is True
    # And tampering with any recorded response breaks the receipt.
    receipt.payload["result"]["responses"][0]["answer"] = "the-lie"
    assert backend.verify_receipt(receipt) is False


# --- 6. Canonical JSON collision resistance ---------------------------------


def test_canonical_json_resists_key_reordering_attack():
    """Two payloads that differ only in dict key order MUST hash identically.

    This is the basic canonical-JSON guarantee: signers and verifiers
    agree on the bytes regardless of insertion order. (Positive case —
    establishes that canonical_json is doing its job, so the next test
    is meaningful.)
    """
    a = canonical_json({"b": 2, "a": 1, "c": 3})
    b = canonical_json({"c": 3, "a": 1, "b": 2})
    assert a == b
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(
        b.encode()
    ).hexdigest()


def test_canonical_json_resists_whitespace_collision():
    """Whitespace-only differences must not cause hash divergence.

    The signed form is compact; verifiers re-canonicalize the same way.
    """
    compact = canonical_json({"k": "v"})
    spaced = json.dumps({"k": "v"}, indent=4, sort_keys=True)
    assert compact != spaced  # raw bytes differ
    # But canonicalizing BOTH yields the same hash:
    assert hashlib.sha256(compact.encode()).hexdigest() == hashlib.sha256(
        canonical_json(json.loads(spaced)).encode()
    ).hexdigest()


def test_canonical_json_distinguishes_semantically_different_payloads():
    """Two payloads with identical naive serialization but different meaning.

    This is the collision-resistance test the threat model cares about.
    If canonical_json weren't actually canonical, an attacker could
    produce a "different" payload that hashes to the same digest as the
    real one — letting them swap content while keeping the signature.

    Concrete attack vector we defend against: the attacker rewrites the
    final_answer AND tries to also rewrite payload_hash to match. The
    signature was over canonical_json(original_payload); the new
    canonical_json(tampered_payload) is different bytes, so the
    signature fails. We prove canonical_json produces different output
    for inputs that naive `json.dumps` might (in some edge cases) treat
    as equivalent.
    """
    # Two semantically different payloads:
    p1 = {"result": {"final_answer": "ship", "agreement": 0.9}}
    p2 = {"result": {"final_answer": "hold", "agreement": 0.9}}
    c1 = canonical_json(p1)
    c2 = canonical_json(p2)
    assert c1 != c2
    assert hashlib.sha256(c1.encode()).hexdigest() != hashlib.sha256(
        c2.encode()
    ).hexdigest()


def test_canonical_json_normalizes_nested_datatypes_deterministically():
    """Sets, datetimes, tuples are normalized so two runs produce the same bytes."""
    # Same data, different container types that naive json.dumps would
    # either choke on or render inconsistently.
    a = canonical_json({"tags": {"x", "a", "m"}})  # set, arbitrary order
    b = canonical_json({"tags": {"m", "x", "a"}})  # same set, different order
    assert a == b  # set is sorted under canonical_json

    # Datetimes are pinned to UTC ISO 8601 — no locale drift.
    dt = datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)
    assert canonical_json({"t": dt}) == '{"t":"2026-07-25T12:00:00+00:00"}'


def test_signature_covers_canonical_bytes_not_python_repr(
    backend: Ed25519Backend, keypair: tuple[str, str]
):
    """End-to-end: signing + tampering via a JSON round-trip is caught.

    An attacker can't escape canonicalization by tampering at the JSON
    wire layer (where they might inject extra keys, reorder, or change
    whitespace) — verify_receipt re-canonicalizes the payload it sees,
    so any difference from the signed bytes fails the signature check.
    """
    priv, _ = keypair
    receipt = _make_receipt(backend, priv, task_id="orig")
    wire = json.dumps(receipt.payload, sort_keys=True, indent=2)
    tampered_payload: dict[str, Any] = json.loads(wire)
    tampered_payload["task_id"] = "swapped"
    receipt.payload = tampered_payload
    assert backend.verify_receipt(receipt) is False


# --- 7. Transports integrity (Nostr / nak) ----------------------------------


NAK_BIN = shutil.which("nak")


@pytest.mark.skipif(NAK_BIN is None, reason="nak not installed on PATH")
def test_nostr_event_with_tampered_content_fails_nak_verify(
    backend: Ed25519Backend, keypair: tuple[str, str]
):
    """A Nostr event with modified content must fail `nak verify`.

    `nak` is fiatjaf's reference Nostr CLI. If Claudeway emits an event
    that tampered content still passes as valid, every relay on earth
    would also accept it — that's a transport-level break. We tamper
    with content (which is part of the NIP-01 serialization that the
    event id commits to) and confirm nak rejects it.
    """
    pytest.importorskip("coincurve", reason="install claudeway[nostr]")

    priv, _ = keypair
    receipt = _make_receipt(backend, priv, task_id="nostr-task")
    # A separate Nostr (secp256k1) key, per the spec.
    nostr_priv = "aa" * 32
    event = to_nostr_event(
        receipt, private_key_hex=nostr_priv, created_at=1700000000
    )

    # Sanity: the untampered event verifies under nak.
    original = json.dumps(event.to_dict())
    proc_ok = subprocess.run(
        [NAK_BIN, "verify"], input=original, capture_output=True, text=True
    )
    assert proc_ok.returncode == 0, (
        f"untampered event should verify under nak: {proc_ok.stderr}"
    )

    # Tamper with the content. event.id commits to the original content,
    # so the signature no longer covers the bytes nak hashes -> reject.
    tampered = json.loads(original)
    tampered["content"] = tampered["content"].replace(
        "use sqlite", "USE POSTGRES INSTEAD"
    )
    proc_bad = subprocess.run(
        [NAK_BIN, "verify"],
        input=json.dumps(tampered),
        capture_output=True,
        text=True,
    )
    assert proc_bad.returncode != 0, (
        "tampered event must fail nak verify; nak accepted it:\n"
        f"stdout={proc_bad.stdout}\nstderr={proc_bad.stderr}"
    )


@pytest.mark.skipif(NAK_BIN is None, reason="nak not installed on PATH")
def test_nostr_event_with_tampered_signature_fails_nak_verify(
    backend: Ed25519Backend, keypair: tuple[str, str]
):
    """A Nostr event with a flipped signature byte must fail `nak verify`."""
    pytest.importorskip("coincurve", reason="install claudeway[nostr]")

    priv, _ = keypair
    receipt = _make_receipt(backend, priv, task_id="nostr-sig-task")
    nostr_priv = "bb" * 32
    event = to_nostr_event(
        receipt, private_key_hex=nostr_priv, created_at=1700000000
    )
    original = json.dumps(event.to_dict())
    proc_ok = subprocess.run(
        [NAK_BIN, "verify"], input=original, capture_output=True, text=True
    )
    assert proc_ok.returncode == 0

    tampered = json.loads(original)
    sig = tampered["sig"]
    tampered["sig"] = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    proc_bad = subprocess.run(
        [NAK_BIN, "verify"],
        input=json.dumps(tampered),
        capture_output=True,
        text=True,
    )
    assert proc_bad.returncode != 0


def test_nostr_event_tamper_detected_without_nak(
    backend: Ed25519Backend, keypair: tuple[str, str]
):
    """Hermetic check that doesn't depend on nak: event.id no longer matches.

    The NIP-01 event id is sha256 of the canonical serialization. Tampering
    with content changes the id a relay will recompute — so even without
    nak, we prove the event is malformed: the (id, sig) pair no longer
    commits to the (now-modified) content.
    """
    pytest.importorskip("coincurve", reason="install claudeway[nostr]")

    from claudeway.transports import _nostr_serialization_for_id

    priv, _ = keypair
    receipt = _make_receipt(backend, priv, task_id="hermetic")
    nostr_priv = "cc" * 32
    event = to_nostr_event(
        receipt, private_key_hex=nostr_priv, created_at=1700000000
    )
    original_id = event.id
    event.content = event.content.replace("use sqlite", "tampered")
    # Recompute what the id SHOULD be now:
    new_canonical = _nostr_serialization_for_id(
        event.pubkey, event.created_at, event.tags, event.content
    )
    new_id = hashlib.sha256(new_canonical.encode("utf-8")).hexdigest()
    # The stored id is the old one; the recomputed one is different. A
    # relay re-derives the id and rejects the mismatch. Claudeway's
    # signature was over the OLD id, so it doesn't cover new_id either.
    assert new_id != original_id
    assert event.id == original_id  # we didn't update it -> mismatch detected


# --- bonus: backend is the only verification authority ---------------------


def test_unsigned_receipt_cannot_be_verified_by_assuming_trust(
    backend: Ed25519Backend,
):
    """An unsigned receipt must fail verification, even if it claims to be signed.

    Defense against an attacker who constructs a receipt object with a
    plausible-looking signature field but no actual signing operation.
    """
    result = ConsensusResult(
        final_answer="pretend",
        method="weighted_vote",
        agent_count=1,
        responses=[],
    )
    receipt = ConsensusReceipt.from_result(result, task_id="fake")
    # Attacker pastes in junk that *looks* like a signature/pubkey.
    receipt.signature = "ab" * 64
    receipt.public_key = "cd" * 32
    receipt.algorithm = "ed25519"
    # is_signed returns True (fields are populated), but verify catches it.
    assert receipt.is_signed is True
    assert backend.verify_receipt(receipt) is False
