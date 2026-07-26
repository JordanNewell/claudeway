"""
Transparency log tests — RFC 6962 Merkle correctness, end-to-end.

Three layers, matching the test_nostr.py pattern:

  - Known-answer / cross-impl: my root matches Google's reference
    ct/crypto/merkle.py `_hash_full` byte-for-byte across many tree sizes.
    This is the credibility-critical proof — same role as the BIP-340
    vectors in test_nostr.py.

  - Property sweep: for many tree sizes (incl. awkward non-power-of-two
    ones), every leaf's inclusion proof verifies against the root; tamper
    detection works; append-stability holds.

  - Receipt-level: the public API on real ConsensusReceipts. The whole
    point — verify a receipt was in a log using only the receipt + the
    proof + the published root, no log instance.

  - Nostr anchor (gated, like test_nostr.py): publish a LogAnchor as a
    NIP-78 event, read back, root matches.
"""

import hashlib

import pytest

from claudeway.consensus import ConsensusResult
from claudeway.signing import ConsensusReceipt
from claudeway.swarm import AgentResponse
from claudeway.transparency import (
    InclusionProof,
    LogAnchor,
    TransparencyLog,
    _root_at_size,
    leaf_hash,
    node_hash,
)

# --- Helpers ----------------------------------------------------------------


def _receipt(answer: str, idx: int) -> ConsensusReceipt:
    """Build a deterministically-distinct receipt for test purposes."""
    result = ConsensusResult(
        final_answer=answer,
        method="weighted_vote",
        agent_count=2,
        responses=[AgentResponse(agent_name="A", answer=answer, confidence=0.9)],
        agreement=0.9,
        rounds=1,
        disagreed=False,
    )
    return ConsensusReceipt.from_result(result, swarm_name="Test", task_id=f"t-{idx}")


# --- RFC 6962 hashing primitives --------------------------------------------


def test_leaf_hash_uses_0x00_domain_separator():
    """RFC 6962 §2.1: leaf = SHA-256(0x00 || data). Domain separation matters."""
    receipt = _receipt("a", 0)
    canonical = receipt.canonical_payload().encode("utf-8")
    expected = hashlib.sha256(b"\x00" + canonical).digest()
    assert leaf_hash(receipt) == expected


def test_node_hash_uses_0x01_domain_separator():
    """RFC 6962 §2.1: node = SHA-256(0x01 || L || R)."""
    left = b"\x11" * 32
    right = b"\x22" * 32
    expected = hashlib.sha256(b"\x01" + left + right).digest()
    assert node_hash(left, right) == expected


def test_empty_log_root_is_sha256_of_empty():
    """Empty log has a defined, publishable root before any receipts."""
    log = TransparencyLog()
    assert log.root == hashlib.sha256(b"").digest()
    assert log.size == 0


# --- Cross-impl KAV: my root vs Google's ct/crypto/merkle.py ----------------


def _google_hash_full(leaves: list[bytes], l_idx: int, r_idx: int) -> bytes:
    """Reference implementation of Google CT's _hash_full root computation.

    Inlined here (BSD-3 licensed in source) ONLY for cross-validation in
    tests — not in the shipping module. Source:
    github.com/google/certificate-transparency/python/ct/crypto/merkle.py.
    Treats `leaves` as already-leaf-hashed (the leaf prefix is applied
    before this function runs in real CT; here we apply it once upstream).
    """
    width = r_idx - l_idx
    if width == 0:
        return hashlib.sha256(b"").digest()
    if width == 1:
        return leaves[l_idx]
    split = 2 ** ((width - 1).bit_length() - 1)
    l_root = _google_hash_full(leaves, l_idx, l_idx + split)
    r_root = _google_hash_full(leaves, l_idx + split, r_idx)
    return hashlib.sha256(b"\x01" + l_root + r_root).digest()


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 32, 33,
                                  100, 127, 128, 200, 511, 512, 513, 1000])
def test_root_matches_google_reference(size: int) -> None:
    """My root byte-matches Google's reference CT impl across many tree shapes.

    This is the credibility KAV: if my Merkle math agrees with the
    reference implementation that real CT logs use, the math is right.
    """
    raw = [bytes([i % 256]) * 4 for i in range(size)]
    leaves = [hashlib.sha256(b"\x00" + d).digest() for d in raw]

    mine = _root_at_size(leaves, size)
    theirs = _google_hash_full(leaves, 0, size)
    assert mine == theirs, f"root mismatch at size={size}"


# --- Property sweep: every leaf verifies ------------------------------------


@pytest.mark.parametrize("size", [0, 1, 2, 3, 4, 5, 7, 8, 9, 16, 17, 31, 32,
                                  100, 127, 128, 129, 500])
def test_every_leaf_verifies(size: int) -> None:
    """For each size, every leaf's inclusion proof verifies against the root.

    Covers power-of-two AND awkward non-power-of-two trees (the case that
    broke earlier hand-rolled impls). This is the core correctness claim.
    """
    log = TransparencyLog()
    receipts = [_receipt(f"a{i}", i) for i in range(size)]
    for r in receipts:
        log.append(r)

    if size == 0:
        assert log.root == hashlib.sha256(b"").digest()
        return

    for i in range(size):
        proof = log.inclusion_proof(i)
        assert TransparencyLog.verify_inclusion(receipts[i], proof, log.root), \
            f"leaf {i} in size {size} did not verify"


def test_inclusion_proof_rejects_out_of_range_index():
    log = TransparencyLog()
    for i in range(3):
        log.append(_receipt(f"a{i}", i))
    with pytest.raises(IndexError):
        log.inclusion_proof(3)
    with pytest.raises(IndexError):
        log.inclusion_proof(-1)


# --- Tamper detection --------------------------------------------------------


def test_tampered_receipt_fails_verification():
    """Mutating a receipt after it was logged invalidates its proof."""
    log = TransparencyLog()
    receipts = [_receipt(f"a{i}", i) for i in range(5)]
    for r in receipts:
        log.append(r)

    proof = log.inclusion_proof(2)
    assert TransparencyLog.verify_inclusion(receipts[2], proof, log.root)

    # Tamper: change the answer, recompute the receipt's payload hash.
    tampered = _receipt("DIFFERENT", 2)
    assert not TransparencyLog.verify_inclusion(tampered, proof, log.root)


def test_tampered_audit_path_fails():
    """Mutating any byte of the audit path breaks verification."""
    log = TransparencyLog()
    for i in range(6):
        log.append(_receipt(f"a{i}", i))

    proof = log.inclusion_proof(3)
    root = log.root
    receipt = _receipt("a3", 3)

    # Flip a byte in one sibling hash.
    bad_path = list(proof.audit_path)
    bad_path[0] = bytes(bad_path[0][0] ^ 0xFF) + bad_path[0][1:]
    bad_proof = InclusionProof(leaf_index=proof.leaf_index, tree_size=proof.tree_size,
                               audit_path=bad_path)
    assert not TransparencyLog.verify_inclusion(receipt, bad_proof, root)


def test_wrong_root_fails():
    """A proof for one root doesn't verify against a different root."""
    log_a = TransparencyLog()
    log_b = TransparencyLog()
    for i in range(4):
        log_a.append(_receipt(f"a{i}", i))
        log_b.append(_receipt(f"b{i}", i))  # different receipts -> different root

    proof = log_a.inclusion_proof(0)
    receipt = _receipt("a0", 0)
    # Should verify against log_a's root, NOT log_b's.
    assert TransparencyLog.verify_inclusion(receipt, proof, log_a.root)
    assert not TransparencyLog.verify_inclusion(receipt, proof, log_b.root)


# --- Append-stability (the day-2 consistency-proof preview) -----------------


def test_proof_remains_valid_after_more_appends():
    """A proof issued at size N still verifies at size N+k against the size-N root.

    This is what makes the log auditable: an old anchor + an old proof +
    the receipt still proves the receipt was in the log at that point in
    history, even as the log keeps growing.
    """
    log = TransparencyLog()
    receipts = [_receipt(f"a{i}", i) for i in range(4)]
    for r in receipts:
        log.append(r)

    snapshot_root = log.root
    snapshot_proof = log.inclusion_proof(1)

    # Append more — log grows, root changes, but the snapshot proof+root
    # still validate the same receipt.
    for i in range(10):
        log.append(_receipt(f"more{i}", 100 + i))

    assert log.root != snapshot_root  # root moved on
    assert TransparencyLog.verify_inclusion(receipts[1], snapshot_proof, snapshot_root)


# --- Standalone verification (the design's central promise) -----------------


def test_verify_inclusion_needs_no_log_instance():
    """The whole point: verify with just (receipt, proof, root) — no log.

    Anyone, anywhere, can confirm a receipt was in a log Claudeway
    published, without trusting Claudeway to run the verification.
    """
    # Side A: Claudeway publishes the log + an anchor + per-receipt proofs.
    log = TransparencyLog()
    for i in range(7):
        log.append(_receipt(f"a{i}", i))
    anchor_root = log.root
    receipt_3 = _receipt("a3", 3)
    proof_3 = log.inclusion_proof(3)

    # Side B: a third party. Has the receipt, the proof, and the published
    # root. No TransparencyLog object. No access to the original leaves.
    assert TransparencyLog.verify_inclusion(receipt_3, proof_3, anchor_root)


# --- Nostr anchor (NIP-78) --------------------------------------------------
#
# Anchors are Nostr events, so they need coincurve (the [nostr] extra).
# Skips cleanly when absent — same pattern as test_nostr.py.

pytest.importorskip("coincurve", reason="install claudeway[nostr]")

import json  # noqa: E402
import os  # noqa: E402

from claudeway.transports import (  # noqa: E402
    NOSTR_TRANSPARENCY_D_TAG,
    NOSTR_TRANSPARENCY_KIND,
    _nostr_pubkey,
    to_log_anchor_event,
)


def _nostr_key() -> str:
    """32-byte hex Nostr private key for the anchor tests."""
    return "11" * 32


def test_anchor_event_is_nip78_with_transparency_d_tag():
    """Anchors are kind-30078 events scoped by `claudeway-transparency`."""
    from datetime import datetime

    log = TransparencyLog()
    for i in range(3):
        log.append(_receipt(f"a{i}", i))
    anchor = LogAnchor(tree_size=log.size, root=log.root, published_at=datetime.utcnow())

    event = to_log_anchor_event(anchor, _nostr_key(), log_name="test", created_at=1700000000)

    assert event.kind == NOSTR_TRANSPARENCY_KIND == 30078
    d_tags = [t for t in event.tags if t[0] == "d"]
    assert d_tags == [["d", NOSTR_TRANSPARENCY_D_TAG]]
    # Log name appears as a `name` tag so consumers can filter by log identity.
    name_tags = [t for t in event.tags if t[0] == "name"]
    assert name_tags == [["name", "test"]]


def test_anchor_event_id_is_sha256_of_nip01_serialization():
    """NIP-01: id == sha256(JSON.stringify([0, pubkey, created_at, kind, tags, content]))."""
    from datetime import datetime

    log = TransparencyLog()
    log.append(_receipt("a", 0))
    anchor = LogAnchor(tree_size=1, root=log.root, published_at=datetime.utcnow())

    event = to_log_anchor_event(anchor, _nostr_key(), log_name="x", created_at=1700000000)

    canonical = json.dumps(
        [0, event.pubkey, event.created_at, event.kind, event.tags, event.content],
        separators=(",", ":"),
    )
    expected_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert event.id == expected_id


def test_anchor_event_pubkey_matches_nostr_key_derivation():
    """Anchor pubkey is the x-only secp256k1 derived from the Nostr private key."""
    from datetime import datetime

    anchor = LogAnchor(tree_size=0, root=hashlib.sha256(b"").digest(),
                       published_at=datetime.utcnow())
    event = to_log_anchor_event(anchor, _nostr_key(), created_at=1700000000)
    assert event.pubkey == _nostr_pubkey(_nostr_key())


def test_anchor_event_content_carries_tree_size_and_root():
    """The anchor content is the JSON LogAnchor — tree_size + hex root recoverable."""
    from datetime import datetime

    log = TransparencyLog()
    for i in range(7):
        log.append(_receipt(f"leaf{i}", i))
    anchor = LogAnchor(tree_size=log.size, root=log.root, published_at=datetime.utcnow())
    event = to_log_anchor_event(anchor, _nostr_key(), log_name="claudeway")

    payload = json.loads(event.content)
    assert payload["tree_size"] == 7
    assert payload["root"] == log.root.hex()
    assert payload["type"] == "claudeway.transparency.anchor.v1"
    assert payload["log_name"] == "claudeway"


RELAY_URL = os.environ.get("CLAUDEWAY_TEST_RELAY")


@pytest.mark.skipif(
    not RELAY_URL,
    reason="set CLAUDEWAY_TEST_RELAY=ws://localhost:10547 to run integration test",
)
@pytest.mark.asyncio
async def test_anchor_event_publishes_and_reads_back():
    """End-to-end: publish an anchor to a relay, read it back, root matches.

    Relays MUST reject malformed Schnorr signatures per NIP-01, so a
    successful round trip is also proof the anchor signature is valid.
    Same shape as test_nostr.py's relay round-trip test.
    """
    import asyncio
    from datetime import datetime

    import websockets

    log = TransparencyLog()
    for i in range(3):
        log.append(_receipt(f"relay{i}", i))
    anchor = LogAnchor(tree_size=log.size, root=log.root, published_at=datetime.utcnow())
    event = to_log_anchor_event(anchor, _nostr_key(), log_name="integration")

    async with websockets.connect(RELAY_URL) as ws:
        await ws.send(json.dumps(["EVENT", event.to_dict()]))
        for _ in range(10):
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            msg = json.loads(raw)
            if msg[0] == "OK" and msg[1] == event.id:
                assert msg[2] is True, f"relay rejected anchor: {msg}"
                break

        sub = ["REQ", "anchor-test",
               {"kinds": [NOSTR_TRANSPARENCY_KIND], "authors": [event.pubkey]}]
        await ws.send(json.dumps(sub))
        seen = None
        for _ in range(10):
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            msg = json.loads(raw)
            if msg[0] == "EVENT" and msg[1] == "anchor-test":
                seen = msg[2]
                break
        await ws.send(json.dumps(["CLOSE", "anchor-test"]))

    assert seen is not None, "did not receive our anchor back from relay"
    payload = json.loads(seen["content"])
    assert payload["root"] == log.root.hex()
    assert payload["tree_size"] == 3
