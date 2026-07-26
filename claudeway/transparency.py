"""
Claudeway transparency log — globally auditable consensus history.

Today the moat is "signed, tamper-evident attestations": Claudeway signs a
receipt, anyone can verify the signature. But "verify the signature" still
requires trusting Claudeway to *show you* the receipt. A receipt that was
secretly altered and re-signed, or quietly removed, leaves no trace.

This module closes that gap. Every signed receipt is appended to an
append-only Merkle log; the log root is published as a Nostr event. Now:

  - **Issuance is provable.** Anyone can verify a receipt was in the log
    at a given root, with an inclusion proof — no Claudeway trust required.
  - **Removal is detectable.** Append-only means a published root commits
    to every leaf before it. Re-anchoring a missing leaf changes the root.
  - **History is auditable.** The Nostr event stream IS the log's history;
    anyone watching sees every anchor Claudeway publishes.

This is Certificate Transparency (RFC 6962) for agent consensus — adapted
to receipts-as-leaves, anchored to Nostr on day 1, with Bitcoin anchoring
via OpenTimestamps (NIP-3) planned for day 2.

The Merkle math is RFC 6962 §2.1 verbatim:
  - leaf hash:  SHA-256(0x00 || leaf_data)
  - node hash:  SHA-256(0x01 || L || R)
The 0x00/0x01 domain separation prevents second-preimage attacks. The
"tree at size N" construction makes inclusion proofs stable across
appends — a proof issued at size N still verifies at size N+k.

Day-1 honesty: a *cryptographically* global log needs a finality anchor
(Bitcoin, day 2). Day 1 gives one logical log per Nostr key, globally
visible and tamper-evident via Nostr's signature model. The canonical
Claudeway log lives under a Claudeway-published Nostr key; anyone can run
their own log under their own key. Day-2 Bitcoin anchoring turns
"tamper-evident" into "tamper-proof."
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .signing import ConsensusReceipt


# --- RFC 6962 hashing -------------------------------------------------------

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"


def leaf_hash(receipt: ConsensusReceipt) -> bytes:
    """RFC 6962 §2.1 leaf hash for a receipt: SHA-256(0x00 || canonical_payload).

    The leaf data is the receipt's canonical payload bytes — the exact string
    its signature is computed over. This binds the log to the same data the
    Ed25519 receipt signature covers: tampering with the receipt invalidates
    both the signature AND any inclusion proof that referenced it.
    """
    canonical = receipt.canonical_payload().encode("utf-8")
    return hashlib.sha256(_LEAF_PREFIX + canonical).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """RFC 6962 §2.1 intermediate node: SHA-256(0x01 || left || right)."""
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


# --- Inclusion proof --------------------------------------------------------


@dataclass
class InclusionProof:
    """
    Proof that a leaf at `leaf_index` is included in the tree of `tree_size`
    with a particular root.

    `audit_path` is the list of sibling hashes from the leaf up to the root,
    bottom-up. Each sibling is paired with the running hash per RFC 6962's
    inclusion-proof verification (§2.1.1): if the leaf is a left child the
    sibling is on the right, vice versa, determined by the bit at the
    current level of the index.

    Standalone — verify_inclusion needs only this, the leaf, and the root.
    No log instance required.
    """

    leaf_index: int
    tree_size: int
    audit_path: list[bytes] = field(default_factory=list)


# --- The log ----------------------------------------------------------------


class TransparencyLog:
    """
    Append-only Merkle log of consensus receipts.

    The only mutator is `append`. No deletion, no reordering — append-only
    is the guarantee that makes the log auditable. Each append returns the
    leaf's sequence index (0-based).

    Roots and proofs are computed on demand; for a small log this is cheap.
    A production log would cache the right-edge sub-trees (RFC 6962 "lazy
    root") — out of scope for day 1, where logs are small and per-key.
    """

    def __init__(self, name: str = "claudeway") -> None:
        self.name = name
        # Stored as leaf hashes (not receipts) so the log doesn't hold
        # payload data it doesn't need. Receipts are reproducible from
        # their canonical payload; the leaf hash binds them.
        self._leaves: list[bytes] = []

    def append(self, receipt: ConsensusReceipt) -> int:
        """Append a receipt's leaf hash. Returns the new leaf's index."""
        index = len(self._leaves)
        self._leaves.append(leaf_hash(receipt))
        return index

    @property
    def size(self) -> int:
        """Number of leaves currently in the log."""
        return len(self._leaves)

    @property
    def root(self) -> bytes:
        """Current Merkle root (32 bytes). Empty log -> SHA-256 of nothing.

        The empty-log root is a defined value (hash of empty string) so
        a freshly-anchored log has a publishable root before any receipts.
        """
        return _root_at_size(self._leaves, len(self._leaves))

    def inclusion_proof(self, leaf_index: int) -> InclusionProof:
        """Build an inclusion proof for the leaf at `leaf_index`.

        Raises IndexError if the index isn't in the current log.
        """
        if not 0 <= leaf_index < len(self._leaves):
            raise IndexError(f"leaf_index {leaf_index} out of range (size {len(self._leaves)})")
        audit_path = _audit_path(self._leaves, leaf_index, len(self._leaves))
        return InclusionProof(
            leaf_index=leaf_index,
            tree_size=len(self._leaves),
            audit_path=audit_path,
        )

    @staticmethod
    def verify_inclusion(
        receipt: ConsensusReceipt,
        proof: InclusionProof,
        expected_root: bytes,
    ) -> bool:
        """
        Verify a receipt was in a log with `expected_root`, using `proof`.

        Static: needs no log instance. The receipt + proof + published root
        is enough — that's the whole point. Anyone, anywhere, can verify.

        Returns False on any mismatch (wrong leaf, tampered path, wrong
        root). Returns True iff the proof chains the receipt's leaf hash
        to `expected_root`.
        """
        leaf = leaf_hash(receipt)
        computed = _verify_path(leaf, proof.leaf_index, proof.tree_size, proof.audit_path)
        return computed == expected_root


# --- Log anchor (a published snapshot) --------------------------------------


@dataclass
class LogAnchor:
    """
    A published snapshot of the log — emitted as a NIP-78 event.

    Anchors commit to a tree_size + root at a point in time. A sequence of
    anchors forms the log's auditable history: anyone watching the Nostr
    stream sees every published root, and can detect a missing or replaced
    anchor (day-2 consistency proofs make this rigorous; day 1 relies on
    Nostr's own append-only-on-relay semantics + the operator's reputation).
    """

    tree_size: int
    root: bytes  # 32 raw bytes; serialize as hex
    published_at: datetime
    nostr_event_id: str | None = None  # set once published

    def to_dict(self) -> dict:
        return {
            "type": "claudeway.transparency.anchor.v1",
            "log_name": "",  # filled by the publisher (to_log_anchor_event)
            "tree_size": self.tree_size,
            "root": self.root.hex(),
            "published_at": self.published_at.isoformat(),
            "nostr_event_id": self.nostr_event_id,
        }


# --- RFC 6962 Merkle internals ----------------------------------------------
#
# We use the recursive "hash sub-tree" formulation from RFC 6962 §2.1.1
# directly. It's the clearest expression of the spec and the tree sizes
# Claudeway deals with (per-key, day 1) are small; recursion depth is
# ~log2(size), so even a million-leaf log only recurses 20 deep.
#
# The spec defines a "Merkle subtree hash" over a half-open range [start,
# end) of leaves. The root is _subtree_hash(0, size). The key invariant
# that makes proofs stable: the tree at size N is built from the same
# sub-trees regardless of what's appended later — a leaf at index i in
# a tree of size N has the same path it would in a tree of size N+k.
#
# Audit paths and verification follow RFC 6962 §2.1.1's algorithm exactly:
# at each level, look at the relevant bit of the leaf index to decide
# whether the sibling is on the left or the right.


def _subtree_hash(leaves: list[bytes], start: int, end: int) -> bytes:
    """Hash the leaves in [start, end) per RFC 6962.

    [start, end) must be non-empty. A single-leaf range returns that leaf.
    Otherwise the range is split at the largest power of two strictly less
    than (end - start), and node_hash merges the two halves.
    """
    assert end > start
    if end - start == 1:
        return leaves[start]
    # Largest power of two strictly less than the range length. This gives
    # a left sub-tree that's a perfect binary tree, leaving the rest on
    # the right — exactly the RFC 6962 shape.
    k = 1
    while k * 2 < end - start:
        k *= 2
    left = _subtree_hash(leaves, start, start + k)
    right = _subtree_hash(leaves, start + k, end)
    return node_hash(left, right)


def _root_at_size(leaves: list[bytes], size: int) -> bytes:
    """Merkle root of the first `size` leaves. Empty -> sha256(b'')."""
    if size == 0:
        return hashlib.sha256(b"").digest()
    return _subtree_hash(leaves, 0, size)


def _audit_path(leaves: list[bytes], leaf_index: int, tree_size: int) -> list[bytes]:
    """RFC 6962 §2.1.1 audit path: sibling hashes, top-down (rootward).

    Walks the tree using the same `last_node = tree_size - 1` discipline as
    _verify_path (and as Google's reference ct/crypto/merkle.py). At each
    level, the leaf either has a sibling at this level (consume one) or is
    the rightmost node of an incomplete level (no sibling, just go up).
    The condition for "has a sibling at this level" matches _verify_path
    exactly: `node_index % 2 OR node_index < last_node`.

    The sibling's hash is recovered from the full leaves by computing the
    hash of the appropriate (sub)tree range via _subtree_hash. We track
    the sibling's range as we walk: when the leaf is a left child, its
    sibling is the right neighbour (range [leaf+1, ...]); when the leaf
    is a right child, the sibling is the left neighbour (range [..., leaf]).
    The ranges are kept in absolute coordinates for _subtree_hash.
    """
    path: list[bytes] = []
    node = leaf_index
    last = tree_size - 1
    # Sibling range trackers, in absolute leaf indices. The current node
    # occupies a 1-leaf "block" starting at `node * block` of size `block`.
    # We grow the block as we walk up; the sibling block is adjacent.
    block = 1
    while last > 0:
        if node % 2 or node < last:
            # There's a sibling at this level. Find its range.
            if node % 2:
                # Node is a right child -> sibling is on the left.
                sib_start = (node - 1) * block
                sib_end = node * block
            else:
                # Node is a left child (and node < last) -> sibling on right.
                sib_start = (node + 1) * block
                sib_end = min((node + 2) * block, tree_size)
            path.append(_subtree_hash(leaves, sib_start, sib_end))
        node //= 2
        last //= 2
        block *= 2
    return path


def _verify_path(leaf: bytes, leaf_index: int, tree_size: int, path: list[bytes]) -> bytes:
    """RFC 6962 §2.1.1 inclusion-proof verification.

    Faithful port of Google's reference ct/crypto/merkle.py algorithm
    (_calculate_root_hash_from_audit_path). Walks the tree from the leaf
    upward; at each level, decides whether a sibling exists by checking
    `node_index % 2 OR node_index < last_node`. The two cases pair the
    sibling on different sides of the running hash.

    The third case — `node_index == last_node` and even — has no sibling
    at this level (the rightmost node of an incomplete level just goes up
    alone, to be paired as a right child at the next level). This is the
    case my earlier hand-rolled impl got wrong for non-power-of-two trees.
    """
    computed = leaf
    node = leaf_index
    last = tree_size - 1
    remaining = list(path)
    while last > 0:
        if not remaining:
            # Proof too short — malformed. Bail; caller compares to root.
            return b""
        if node % 2:
            # Right child: sibling is on the left.
            sibling = remaining.pop(0)
            computed = node_hash(sibling, computed)
        elif node < last:
            # Left child with a right sibling at this level.
            sibling = remaining.pop(0)
            computed = node_hash(computed, sibling)
        # else: node == last and even — no sibling here, go up.
        node //= 2
        last //= 2
    return computed
