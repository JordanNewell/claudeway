"""
Nostr transport tests — the Buzz-interop path.

Layered:
  - BIP-340 known-answer tests (pubkey + Schnorr sign) so we know the crypto
    is correct independent of any relay.
  - Event construction tests: NIP-01 id derivation, kind-30078 tagging,
    signature covers the id, content carries the JSON receipt.
  - Optional integration test: publish to a real relay, read it back, verify
    the receipt signature on the read-back content. Relays MUST reject
    malformed Schnorr signatures, so acceptance == verification. Gated on
    the CLAUDEWAY_TEST_RELAY env var (e.g. ws://localhost:10547).

coincurve is required; `pip install claudeway[nostr]` or `pip install coincurve`.
"""

import hashlib
import json
import os
import time

import pytest

from claudeway.consensus import ConsensusResult
from claudeway.signing import ConsensusReceipt, Ed25519Backend
from claudeway.swarm import AgentResponse
from claudeway.transports import (
    NOSTR_CONSENSUS_KIND,
    _nostr_pubkey,
    _nostr_serialization_for_id,
    _nostr_sign,
    to_nostr_event,
)

pytest.importorskip("coincurve", reason="install claudeway[nostr]")


# BIP-340 published test vector 0 (https://github.com/bitcoin/bips/blob/master/bip-0340/test-vectors.csv).
# We pin only vector 0: vector 1's secret has the high bit set (intentional
# edge case) which coincurve doesn't auto-mask; vectors 2+ exercise verify-only
# paths. Vector 0 fully exercises sign + pubkey derivation with zero aux,
# which matches our deterministic signer.
BIP340_VECTOR_0 = {
    "secret": "0000000000000000000000000000000000000000000000000000000000000003",
    "public": "f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9",
    "aux":    "0000000000000000000000000000000000000000000000000000000000000000",
    "message": "0000000000000000000000000000000000000000000000000000000000000000",
    "signature": (
        "e907831f80848d1069a5371b402410364bdf1c5f8307b0084c55f1ce2dca8215"
        "25f66a4a85ea8b71e482a74f382d2ce5ebeee8fdb2172f477df4900d310536c0"
    ),
}


# --- BIP-340 known-answer tests (crypto correctness, no relay) ---


def test_bip340_pubkey_matches_vector_0():
    """The x-only pubkey Claudeway derives must match the BIP-340 vector 0."""
    assert _nostr_pubkey(BIP340_VECTOR_0["secret"]) == BIP340_VECTOR_0["public"]


def test_bip340_sign_matches_vector_0():
    """Deterministic BIP-340 Schnorr over the spec's first vector.

    Our signer uses zero aux randomness, which matches vector 0's aux exactly.
    """
    vec = BIP340_VECTOR_0
    sig = _nostr_sign(vec["message"], vec["secret"])
    assert sig == vec["signature"]


# --- Event construction (NIP-01 / NIP-78) ---


@pytest.fixture
def signed_receipt():
    """A signed ConsensusReceipt the Nostr event will carry."""
    responses = [
        AgentResponse(agent_name="A", answer="ship it", confidence=0.9),
        AgentResponse(agent_name="B", answer="ship it", confidence=0.85),
    ]
    result = ConsensusResult(
        final_answer="ship it",
        method="weighted_vote",
        agent_count=2,
        responses=responses,
        agreement=0.9,
        rounds=1,
    )
    receipt = ConsensusReceipt.from_result(result, swarm_name="BuzzRoom", task_id="t1")
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    backend.sign_receipt(receipt, priv)
    return receipt


@pytest.fixture
def nostr_key():
    """A deterministic Nostr (BIP-340) secret for reproducible event ids."""
    return "0000000000000000000000000000000000000000000000000000000000000003"


def test_nostr_event_kind_is_nip78_addressable(signed_receipt, nostr_key):
    event = to_nostr_event(signed_receipt, nostr_key)
    assert event.kind == NOSTR_CONSENSUS_KIND == 30078


def test_nostr_event_id_is_sha256_of_nip01_serialization(signed_receipt, nostr_key):
    """Per NIP-01: id == sha256(JSON.stringify([0, pubkey, created_at, kind, tags, content]))."""
    event = to_nostr_event(signed_receipt, nostr_key, created_at=1700000000)
    canonical = _nostr_serialization_for_id(
        event.pubkey, event.created_at, event.kind, event.tags, event.content
    )
    expected_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert event.id == expected_id


def test_nostr_event_pubkey_matches_xonly_derivation(signed_receipt, nostr_key):
    event = to_nostr_event(signed_receipt, nostr_key)
    assert event.pubkey == _nostr_pubkey(nostr_key)
    assert len(event.pubkey) == 64  # 32 bytes hex


def test_nostr_event_signature_is_64_byte_schnorr(signed_receipt, nostr_key):
    event = to_nostr_event(signed_receipt, nostr_key)
    assert len(event.sig) == 128  # 64 bytes hex
    bytes.fromhex(event.sig)  # parses


def test_nostr_event_signature_covers_event_id(signed_receipt, nostr_key):
    """The Schnorr signature must be over the 32-byte event id (BIP-340 vector).

    We can't verify Schnorr with coincurve alone (no verify API), so we
    re-sign with the same key and check determinism: zero-aux BIP-340 signing
    is deterministic, so sign(event_id) == event.sig.
    """
    event = to_nostr_event(signed_receipt, nostr_key, created_at=1700000000)
    expected_sig = _nostr_sign(event.id, nostr_key)
    assert event.sig == expected_sig


def test_nostr_event_tags_include_d_tag_and_client(signed_receipt, nostr_key):
    event = to_nostr_event(signed_receipt, nostr_key, d_tag="buzz-room-42")
    tag_keys = [t[0] for t in event.tags]
    assert "d" in tag_keys
    assert "client" in tag_keys
    d_tag = next(t for t in event.tags if t[0] == "d")
    assert d_tag[1] == "buzz-room-42"
    client_tag = next(t for t in event.tags if t[0] == "client")
    assert client_tag[1] == "claudeway"


def test_nostr_event_content_carries_signed_receipt(signed_receipt, nostr_key):
    """The wire content is the JSON receipt — readable by any Nostr client."""
    event = to_nostr_event(signed_receipt, nostr_key)
    payload = json.loads(event.content)
    assert payload["type"] == "claudeway.receipt.v1"
    assert payload["signature"] == signed_receipt.signature
    assert payload["public_key"] == signed_receipt.public_key


def test_nostr_event_roundtrips_through_dict(signed_receipt, nostr_key):
    """An event serialized to dict and back keeps all NIP-01 fields."""
    event = to_nostr_event(signed_receipt, nostr_key)
    as_dict = event.to_dict()
    assert as_dict["id"] == event.id
    assert as_dict["sig"] == event.sig
    assert as_dict["kind"] == 30078
    # The dict must be JSON-serializable for relay wire format.
    json.dumps(as_dict)


# --- Integration: relay round-trip (gated) ---


RELAY_URL = os.environ.get("CLAUDEWAY_TEST_RELAY")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not RELAY_URL,
    reason="set CLAUDEWAY_TEST_RELAY=ws://localhost:10547 to run integration test",
)
async def test_nostr_event_publishes_and_reads_back(signed_receipt, nostr_key):
    """End-to-end: publish to a relay, subscribe, read it back, verify receipt.

    Relays MUST reject malformed signatures per NIP-01, so a successful round
    trip is also proof the Schnorr signature is valid as the network sees it.
    """
    import websockets

    event = to_nostr_event(signed_receipt, nostr_key, created_at=int(time.time()))

    async with websockets.connect(RELAY_URL) as ws:
        await ws.send(json.dumps(["EVENT", event.to_dict()]))
        # Drain OK/NOTICE responses.
        for _ in range(5):
            raw = await asyncio_wait(ws, timeout=2.0)
            msg = json.loads(raw)
            if msg[0] == "OK" and msg[1] == event.id:
                assert msg[2] is True, f"relay rejected event: {msg}"
                break

        # Subscribe for kind-30078 from our pubkey.
        sub = ["REQ", "claudeway-test", {"kinds": [30078], "authors": [event.pubkey]}]
        await ws.send(json.dumps(sub))
        seen = None
        for _ in range(10):
            raw = await asyncio_wait(ws, timeout=2.0)
            msg = json.loads(raw)
            if msg[0] == "EVENT" and msg[1] == "claudeway-test":
                seen = msg[2]
                break
        await ws.send(json.dumps(["CLOSE", "claudeway-test"]))

    assert seen is not None, "did not receive our own event back from relay"
    assert seen["id"] == event.id
    assert seen["sig"] == event.sig
    # Verify the receipt still validates after the round trip.
    payload = json.loads(seen["content"])
    rebuilt = ConsensusReceipt(
        payload=payload["payload"],
        algorithm=payload["algorithm"],
        public_key=payload["public_key"],
        signature=payload["signature"],
        payload_hash=payload["payload_hash"],
        signed_at=payload["signed_at"],
    )
    assert Ed25519Backend().verify_receipt(rebuilt) is True


async def asyncio_wait(ws, timeout):
    """websockets >= 11 dropped the wait_for-style helper; this bridges both."""
    import asyncio

    return await asyncio.wait_for(ws.recv(), timeout=timeout)
