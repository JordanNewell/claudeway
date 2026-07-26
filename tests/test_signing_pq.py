"""
Post-quantum signing tests — the PQ half of the moat.

Mirrors tests/test_signing.py's surface: sign/verify round-trip, tamper
detection (payload, signature, public_key, payload_hash), wrong-key
rejection, generated-keypair distinctness, and multi-backend coexistence
(the same canonical payload signed by Ed25519 and ML-DSA-65 verifies
under each respective backend).

Skips gracefully when the optional `dilithium-py` dep isn't installed
(`pip install claudeway[pq]`).
"""

import pytest

from claudeway.consensus import ConsensusResult
from claudeway.signing import ConsensusReceipt, Ed25519Backend
from claudeway.signing_pq import MLDSABackend
from claudeway.swarm import AgentResponse

pytest.importorskip("dilithium_py", reason="install with: pip install claudeway[pq]")


@pytest.fixture
def signed_receipt():
    """A freshly ML-DSA-65-signed receipt for tamper/round-trip tests."""
    responses = [
        AgentResponse(agent_name="A", answer="ship mldsa65", confidence=0.9),
        AgentResponse(agent_name="B", answer="ship mldsa65", confidence=0.85),
    ]
    result = ConsensusResult(
        final_answer="ship mldsa65",
        method="weighted_vote",
        agent_count=2,
        responses=responses,
        agreement=0.9,
        rounds=1,
    )
    receipt = ConsensusReceipt.from_result(result, swarm_name="PQReview", task_id="pq1")
    backend = MLDSABackend()
    priv, _ = backend.generate_keypair()
    backend.sign_receipt(receipt, priv)
    return receipt, backend


# --- sign / verify round-trip ---


def test_valid_receipt_verifies(signed_receipt):
    receipt, backend = signed_receipt
    assert receipt.is_signed
    assert receipt.algorithm == "mldsa65"
    assert backend.verify_receipt(receipt) is True


def test_unsigned_receipt_does_not_verify():
    result = ConsensusResult(final_answer="x", method="m", agent_count=1, responses=[])
    receipt = ConsensusReceipt.from_result(result)
    assert not receipt.is_signed
    assert MLDSABackend().verify_receipt(receipt) is False


def test_generated_keypairs_are_distinct():
    backend = MLDSABackend()
    priv1, pub1 = backend.generate_keypair()
    priv2, pub2 = backend.generate_keypair()
    assert priv1 != priv2
    assert pub1 != pub2


# --- tamper detection (the moat) ---


def test_payload_tamper_invalidates_signature(signed_receipt):
    receipt, backend = signed_receipt
    receipt.payload["result"]["final_answer"] = "USE ED25519 ONLY"
    assert backend.verify_receipt(receipt) is False


def test_signature_tamper_invalidates(signed_receipt):
    receipt, backend = signed_receipt
    receipt.signature = "00" * 64  # plausible-looking but wrong
    assert backend.verify_receipt(receipt) is False


def test_wrong_public_key_rejects(signed_receipt):
    receipt, backend = signed_receipt
    _, other_pub = backend.generate_keypair()
    receipt.public_key = other_pub
    assert backend.verify_receipt(receipt) is False


def test_payload_hash_mismatch_rejects(signed_receipt):
    """If someone rewrites payload_hash without re-signing, verification must fail."""
    receipt, backend = signed_receipt
    receipt.payload_hash = "0" * 64
    assert backend.verify_receipt(receipt) is False


# --- multi-backend coexistence ---


def test_same_payload_signs_under_both_backends():
    """The same canonical receipt payload must be signable by either backend
    and verify only under the backend that signed it."""
    result = ConsensusResult(
        final_answer="dual sign",
        method="weighted_vote",
        agent_count=1,
        responses=[],
        agreement=1.0,
        rounds=1,
    )

    ed = Ed25519Backend()
    pq = MLDSABackend()

    ed_priv, _ = ed.generate_keypair()
    pq_priv, _ = pq.generate_keypair()

    ed_receipt = ConsensusReceipt.from_result(result, swarm_name="Dual", task_id="d1")
    pq_receipt = ConsensusReceipt.from_result(result, swarm_name="Dual", task_id="d1")

    ed.sign_receipt(ed_receipt, ed_priv)
    pq.sign_receipt(pq_receipt, pq_priv)

    # Same payload, same hash — different algorithm tag, different signature.
    assert ed_receipt.payload_hash == pq_receipt.payload_hash
    assert ed_receipt.canonical_payload() == pq_receipt.canonical_payload()
    assert ed_receipt.algorithm == "ed25519"
    assert pq_receipt.algorithm == "mldsa65"
    assert ed_receipt.signature != pq_receipt.signature

    # Each verifies under its own backend.
    assert ed.verify_receipt(ed_receipt) is True
    assert pq.verify_receipt(pq_receipt) is True

    # Cross-verification fails: each backend rejects the other's signature
    # (wrong key/sig sizes throw inside the verify primitive, caught by
    # verify_receipt's guard).
    assert ed.verify_receipt(pq_receipt) is False
    assert pq.verify_receipt(ed_receipt) is False
