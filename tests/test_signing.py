"""
Signing + transport tests — the moat.

Covers: canonical serialization determinism, Ed25519 sign/verify, tamper
detection (the whole point), wrong-key rejection, and transport rendering
(JSON receipt, W3C VC). Nostr transport graceful-degradation is tested
separately since it needs an optional native lib.
"""


import pytest

from claudeway.consensus import ConsensusResult
from claudeway.signing import (
    ConsensusReceipt,
    Ed25519Backend,
    canonical_json,
)
from claudeway.swarm import AgentResponse
from claudeway.transports import (
    NOSTR_CONSENSUS_KIND,
    to_json_receipt,
    to_nostr_event,
    to_verifiable_credential,
)


@pytest.fixture
def signed_receipt():
    """A freshly signed receipt for transport/tamper tests."""
    responses = [
        AgentResponse(agent_name="A", answer="use sqlite", confidence=0.9),
        AgentResponse(agent_name="B", answer="use sqlite", confidence=0.85),
    ]
    result = ConsensusResult(
        final_answer="use sqlite",
        method="weighted_vote",
        agent_count=2,
        responses=responses,
        agreement=0.9,
        rounds=1,
    )
    receipt = ConsensusReceipt.from_result(result, swarm_name="DBPicker", task_id="t1")
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    backend.sign_receipt(receipt, priv)
    return receipt, backend


# --- canonical serialization ---


def test_canonical_json_is_deterministic(signed_receipt):
    receipt, _ = signed_receipt
    a = canonical_json(receipt.payload)
    b = canonical_json(receipt.payload)
    assert a == b


def test_canonical_json_is_sorted_and_compact():
    payload = {"b": 1, "a": 2}
    out = canonical_json(payload)
    assert out == '{"a":2,"b":1}'


# --- sign / verify round-trip ---


def test_valid_receipt_verifies(signed_receipt):
    receipt, backend = signed_receipt
    assert receipt.is_signed
    assert backend.verify_receipt(receipt) is True


def test_unsigned_receipt_does_not_verify():
    result = ConsensusResult(final_answer="x", method="m", agent_count=1, responses=[])
    receipt = ConsensusReceipt.from_result(result)
    assert not receipt.is_signed
    assert Ed25519Backend().verify_receipt(receipt) is False


def test_generated_keypairs_are_distinct():
    backend = Ed25519Backend()
    priv1, pub1 = backend.generate_keypair()
    priv2, pub2 = backend.generate_keypair()
    assert priv1 != priv2
    assert pub1 != pub2


# --- tamper detection (the moat) ---


def test_payload_tamper_invalidates_signature(signed_receipt):
    receipt, backend = signed_receipt
    receipt.payload["result"]["final_answer"] = "USE POSTGRES INSTEAD"
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
    # Signature is over canonical_json(payload), which is unchanged, so the
    # crypto verifies — but the hash guard catches the tampering first.
    assert backend.verify_receipt(receipt) is False


# --- transports ---


def test_json_receipt_shape(signed_receipt):
    receipt, _ = signed_receipt
    jr = to_json_receipt(receipt)
    assert jr["type"] == "claudeway.receipt.v1"
    assert jr["signature"] == receipt.signature
    assert jr["public_key"] == receipt.public_key
    assert jr["payload_hash"] == receipt.payload_hash


def test_verifiable_credential_envelope(signed_receipt):
    receipt, _ = signed_receipt
    vc = to_verifiable_credential(receipt, issuer_did="did:web:claudeway.dev")
    assert "VerifiableCredential" in vc["type"]
    assert "ConsensusReceipt" in vc["type"]
    assert vc["proof"]["proofValue"] == receipt.signature
    assert vc["issuer"] == "did:web:claudeway.dev"


def test_json_receipt_roundtrips_through_copy(signed_receipt):
    """Serialization to dict and back must remain verifiable."""
    receipt, backend = signed_receipt
    as_dict = to_json_receipt(receipt)
    # Reconstruct a receipt object from the dict and verify.
    rebuilt = ConsensusReceipt(
        payload=as_dict["payload"],
        algorithm=as_dict["algorithm"],
        public_key=as_dict["public_key"],
        signature=as_dict["signature"],
        payload_hash=as_dict["payload_hash"],
        signed_at=as_dict["signed_at"],
    )
    assert backend.verify_receipt(rebuilt) is True


# --- Nostr transport graceful degradation ---


def test_nostr_event_kind_is_nip78_addressable():
    assert NOSTR_CONSENSUS_KIND == 30078


def test_nostr_transport_requires_optional_lib(signed_receipt):
    """Without coincurve installed, Nostr must give a clear error."""
    receipt, _ = signed_receipt
    try:
        import coincurve  # noqa: F401
        pytest.skip("coincurve installed — native path not exercised here")
    except ImportError:
        pass

    with pytest.raises(ImportError) as exc:
        to_nostr_event(receipt, private_key_hex="aa" * 32)
    assert "claudeway[nostr]" in str(exc.value)
