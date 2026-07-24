"""
Claudeway signing - verifiable, tamper-evident consensus receipts.

This is the moat. A ConsensusResult isn't just "an answer" — it's an
attestation: a canonical payload signed by a key, verifiable by anyone, with
the signature decoupled from how the receipt is transported.

Design (future-proof):
  - ConsensusReceipt: transport-agnostic canonical payload.
  - SignatureBackend (interface): swappable crypto. Ed25519 ships by default
    (no new deps, works everywhere). Nostr/secp256k1 is an opt-in extra for
    Buzz interop. A future ML-DSA post-quantum backend drops in without
    touching consensus code.
  - Transports: the same signed receipt can be emitted as a plain JSON
    receipt, a Nostr event (kind 30078, NIP-78 app data), or a W3C
    Verifiable Credential. Signing is independent of transport.

Why decouple: the W3C AI Agent Protocol CG is converging on VC/DID for agent
attestation; Nostr is one transport; post-quantum signatures are coming.
Hardwiring any one of these would force a rewrite. This layer won't.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .consensus import ConsensusResult

# --- Canonical serialization -------------------------------------------------


def canonical_json(data: Any) -> str:
    """
    Deterministic JSON for signing.

    Sorted keys, no extra whitespace, no non-ASCII escapes, fixed datetime
    rendering. Two processes producing the same receipt MUST hash identically
    so signatures verify across machines and languages.
    """
    return json.dumps(
        _canonicalize(data),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _canonicalize(obj: Any) -> Any:
    """Recursively normalize dataclass/datetime/sets into canonical JSON forms."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _canonicalize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, datetime):
        # ISO 8601, UTC, microsecond precision — stable across locales.
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=UTC)
        return obj.astimezone(UTC).isoformat()
    if isinstance(obj, dict):
        return {str(k): _canonicalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canonicalize(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        # Deterministic order for sets.
        return sorted(_canonicalize(v) for v in obj)
    return obj


# --- Receipt -----------------------------------------------------------------


@dataclass
class ConsensusReceipt:
    """
    A signed (or signable) consensus attestation.

    payload: the canonical consensus facts (answer, agents, agreement...).
    algorithm: which SignatureBackend produced the signature.
    public_key: hex-encoded verification key of the signer.
    signature: hex-encoded signature over sha256(canonical_json(payload)).
    payload_hash: hex sha256 of the canonical payload, for quick comparison.
    signed_at: UTC timestamp of signing.
    metadata: free-form, transport-specific hints (not signed).
    """

    payload: dict[str, Any]
    algorithm: str = ""
    public_key: str = ""
    signature: str = ""
    payload_hash: str = ""
    signed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(
        cls,
        result: ConsensusResult,
        swarm_name: str = "",
        task_id: str = "",
    ) -> ConsensusReceipt:
        """Build an unsigned receipt from a ConsensusResult."""
        payload = {
            "type": "claudeway.consensus.v1",
            "swarm": swarm_name,
            "task_id": task_id,
            "result": result.to_dict(),
        }
        canonical = canonical_json(payload)
        return cls(
            payload=payload,
            payload_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def canonical_payload(self) -> str:
        """Return the exact string that signatures are computed over."""
        return canonical_json(self.payload)

    @property
    def is_signed(self) -> bool:
        return bool(self.signature and self.public_key and self.algorithm)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- Signature backends ------------------------------------------------------


class SignatureBackend(ABC):
    """
    Swappable crypto for signing receipts.

    Implementations: Ed25519Backend (default), and (opt-in) a Nostr/secp256k1
    backend. The interface is intentionally tiny so a future post-quantum
    backend (ML-DSA / SLH-DSA) drops in without changes elsewhere.
    """

    algorithm: str = "abstract"

    @abstractmethod
    def generate_keypair(self) -> tuple[str, str]:
        """Return (private_key_hex, public_key_hex)."""
        ...

    @abstractmethod
    def sign(self, message: bytes, private_key_hex: str) -> str:
        """Sign message bytes; return hex signature."""
        ...

    @abstractmethod
    def verify(self, message: bytes, signature_hex: str, public_key_hex: str) -> bool:
        """Return True iff signature is valid for message under public_key."""
        ...

    # Convenience: sign/verify a whole receipt.

    def sign_receipt(
        self, receipt: ConsensusReceipt, private_key_hex: str
    ) -> ConsensusReceipt:
        """Sign a receipt in place and return it."""
        public_key_hex = self._public_from_private(private_key_hex)
        message = receipt.canonical_payload().encode("utf-8")
        receipt.signature = self.sign(message, private_key_hex)
        receipt.public_key = public_key_hex
        receipt.algorithm = self.algorithm
        receipt.signed_at = datetime.now(UTC).isoformat()
        return receipt

    def verify_receipt(self, receipt: ConsensusReceipt) -> bool:
        """Verify a signed receipt. Unsigned or tampered receipts return False."""
        if not receipt.is_signed:
            return False
        # Re-hash to detect payload tampering post-signing.
        recomputed = hashlib.sha256(receipt.canonical_payload().encode("utf-8"))
        if recomputed.hexdigest() != receipt.payload_hash:
            return False
        message = receipt.canonical_payload().encode("utf-8")
        try:
            return self.verify(message, receipt.signature, receipt.public_key)
        except Exception:
            return False

    def _public_from_private(self, private_key_hex: str) -> str:
        """Default: backends override if deriving the pubkey is cheaper than signing."""
        raise NotImplementedError


class Ed25519Backend(SignatureBackend):
    """
    Default signature backend. Ed25519 over the cryptography lib (already a dep).

    No new native dependencies, works on Windows/Linux/Mac, fast, compact
    (64-byte signatures). Not Nostr-native — use NostrBackend for Buzz interop.
    """

    algorithm = "ed25519"

    def __init__(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
        self._Ed25519PrivateKey = Ed25519PrivateKey  # noqa: class attr, not a secret # gitleaks:allow
        self._Ed25519PublicKey = Ed25519PublicKey

    def generate_keypair(self) -> tuple[str, str]:
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )
        priv = self._Ed25519PrivateKey.generate()
        pub = priv.public_key()
        return (
            priv.private_bytes(
                encoding=Encoding.Raw,
                format=PrivateFormat.Raw,
                encryption_algorithm=NoEncryption(),
            ).hex(),
            pub.public_bytes(
                encoding=Encoding.Raw,
                format=PublicFormat.Raw,
            ).hex(),
        )

    def _public_from_private(self, private_key_hex: str) -> str:
        priv = self._load_private(private_key_hex)
        return priv.public_key().public_bytes(
            encoding=self._enc(),
            format=self._pubfmt(),
        ).hex()

    def sign(self, message: bytes, private_key_hex: str) -> str:
        return self._load_private(private_key_hex).sign(message).hex()

    def verify(self, message: bytes, signature_hex: str, public_key_hex: str) -> bool:
        from cryptography.exceptions import InvalidSignature
        pub = self._load_public(public_key_hex)
        try:
            pub.verify(bytes.fromhex(signature_hex), message)
            return True
        except InvalidSignature:
            return False

    # --- key loading helpers (kept tiny, import at call time) ---

    def _enc(self):
        from cryptography.hazmat.primitives.serialization import Encoding
        return Encoding.Raw

    def _pubfmt(self):
        from cryptography.hazmat.primitives.serialization import PublicFormat
        return PublicFormat.Raw

    def _load_private(self, hex_key: str):
        return self._Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hex_key))

    def _load_public(self, hex_key: str):
        return self._Ed25519PublicKey.from_public_bytes(bytes.fromhex(hex_key))


# --- Default backend helper --------------------------------------------------


def default_backend() -> SignatureBackend:
    """The backend used when callers don't specify one."""
    return Ed25519Backend()
