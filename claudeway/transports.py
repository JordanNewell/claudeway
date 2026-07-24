"""
Claudeway transports - emit a signed ConsensusReceipt over a wire format.

Signing (core.signing) is independent of transport. Here we render the same
signed receipt into formats downstream systems consume:

  - JSONReceipt: plain JSON, the simplest verifiable artifact.
  - NostrEvent (NIP-01/NIP-78): a kind-30078 addressable event carrying the
    receipt, signed per the Nostr spec (Schnorr over secp256k1). Drops into a
    Buzz room or any Nostr relay.
  - VerifiableCredential: W3C VC v2.0-compatible envelope (the direction the
    W3C AI Agent Protocol CG is standardizing on).

Nostr requires secp256k1+Schnorr (BIP-340), which needs a native lib. It's
imported lazily so the core stays dependency-free; install
`claudeway[nostr]` (pynostr / coincurve) to enable NostrEvent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .signing import ConsensusReceipt

# --- JSON receipt ------------------------------------------------------------


def to_json_receipt(receipt: ConsensusReceipt) -> dict[str, Any]:
    """The plain, self-describing JSON form of a receipt."""
    return {
        "type": "claudeway.receipt.v1",
        "payload": receipt.payload,
        "payload_hash": receipt.payload_hash,
        "algorithm": receipt.algorithm,
        "public_key": receipt.public_key,
        "signature": receipt.signature,
        "signed_at": receipt.signed_at,
        "metadata": receipt.metadata,
    }


# --- W3C Verifiable Credential envelope --------------------------------------


def to_verifiable_credential(
    receipt: ConsensusReceipt,
    issuer_did: str = "",
) -> dict[str, Any]:
    """
    Wrap a receipt as a W3C VC v2.0-compatible VerifiableCredential.

    The receipt's signature becomes the proof. `issuer_did` is optional;
    when present it's recorded as the issuer (a DID per the W3C AI Agent
    Protocol direction). This is an envelope — full VC issuer/holder/verifier
    semantics are out of scope here, but the shape is standards-aligned.
    """
    return {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://claudeway.dev/contexts/consensus/v1",
        ],
        "type": ["VerifiableCredential", "ConsensusReceipt"],
        "issuer": issuer_did or f"key:{receipt.public_key}",
        "issuanceDate": receipt.signed_at,
        "credentialSubject": receipt.payload,
        "proof": {
            "type": receipt.algorithm,
            "verificationMethod": f"key:{receipt.public_key}",
            "proofValue": receipt.signature,
            "proofHash": receipt.payload_hash,
        },
    }


# --- Nostr event (NIP-01 / NIP-78) -------------------------------------------


# NIP-78 application-specific data uses kind 30078 (addressable).
NOSTR_CONSENSUS_KIND = 30078


@dataclass
class NostrEvent:
    """A minimal NIP-01 event (enough to publish to a relay)."""

    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: list[list[str]]
    content: str
    sig: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pubkey": self.pubkey,
            "created_at": self.created_at,
            "kind": self.kind,
            "tags": self.tags,
            "content": self.content,
            "sig": self.sig,
        }


def to_nostr_event(
    receipt: ConsensusReceipt,
    private_key_hex: str,
    created_at: int | None = None,
    d_tag: str = "claudeway-consensus",
) -> NostrEvent:
    """
    Render a signed receipt as a Nostr kind-30078 event.

    The receipt itself is already signed by its own backend (Ed25519 by
    default); the Nostr event signature is an *additional* transport-level
    Schnorr signature that relays require. Requires a Nostr (secp256k1)
    private key — distinct from the receipt's signing key by design, so a
    relay's key can rotate without invalidating receipts.

    Lazily imports a BIP-340-capable library. Install `claudeway[nostr]`.
    """
    import time
    created_at = int(time.time()) if created_at is None else int(created_at)

    content = json.dumps(to_json_receipt(receipt), sort_keys=True, separators=(",", ":"))
    tags = [["d", d_tag], ["client", "claudeway"]]
    pubkey = _nostr_pubkey(private_key_hex)

    canonical = _nostr_serialization_for_id(pubkey, created_at, tags, content)
    event_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    sig = _nostr_sign(event_id, private_key_hex)

    return NostrEvent(
        id=event_id,
        pubkey=pubkey,
        created_at=created_at,
        kind=NOSTR_CONSENSUS_KIND,
        tags=tags,
        content=content,
        sig=sig,
    )


# --- Nostr crypto helpers (lazy, native-dep tolerant) ------------------------


def _nostr_serialization_for_id(
    pubkey: str, created_at: int, tags: list[list[str]], content: str
) -> str:
    """The exact JSON array NIP-01 hashes to produce an event id."""
    return json.dumps(
        [0, pubkey, created_at, NOSTR_CONSENSUS_KIND, tags, content],
        separators=(",", ":"),
    )


def _load_nostr_crypto():
    """
    Resolve a BIP-340 Schnorr signer.

    Tries coincurve (preferred, Windows-friendly via pynostr) then secp256k1.
    Raises a clear ImportError with install instructions if neither is present.
    """
    try:
        import coincurve  # type: ignore
        return ("coincurve", coincurve)
    except ImportError:
        pass
    try:
        import secp256k1  # type: ignore
        return ("secp256k1", secp256k1)
    except ImportError:
        raise ImportError(
            "Nostr transport requires a BIP-340 Schnorr library. "
            "Install with: pip install claudeway[nostr] "
            "(provides coincurve/secp256k1)"
        )


def _nostr_pubkey(private_key_hex: str) -> str:
    """Derive the 32-byte hex Nostr pubkey (x-only) from a private key."""
    backend, lib = _load_nostr_crypto()
    if backend == "coincurve":
        priv = lib.PrivateKey(bytes.fromhex(private_key_hex))
        return priv.public_key.format(compressed=True)[1:33].hex()
    # secp256k1 lib
    pk = lib.PrivateKey(bytes.fromhex(private_key_hex))
    return pk.pubkey.format(compressed=True)[1:33].hex()


def _nostr_sign(event_id_hex: str, private_key_hex: str) -> str:
    """Produce a BIP-340 Schnorr signature over the 32-byte event id."""
    backend, lib = _load_nostr_crypto()
    msg = bytes.fromhex(event_id_hex)
    if backend == "coincurve":
        priv = lib.PrivateKey(bytes.fromhex(private_key_hex))
        # coincurve exposes schnorr_sign at module level.
        sig = lib.schnorr_sign(priv.private_key, msg) if hasattr(lib, "schnorr_sign") else None
        if sig is None:
            # Fallback: PrivateKey has no schnorr; use the utils helper.
            import coincurve.utils as cu  # type: ignore
            sig = cu.schnorr_sign(bytes.fromhex(private_key_hex), msg)
        return sig.hex()
    # secp256k1 lib: default aux randomness is fine for receipts.
    pk = lib.PrivateKey(bytes.fromhex(private_key_hex))
    return pk.schnorr_sign(msg, None, raw=True).hex()
