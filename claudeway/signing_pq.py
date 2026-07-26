"""
Claudeway post-quantum signing — ML-DSA-65 backend.

A sibling to Ed25519Backend. Same SignatureBackend interface, same
ConsensusReceipt shape, same canonical_json/payload_hash — only the
signature scheme changes. Receipts pick up algorithm="mldsa65"
automatically when signed via this backend.

ML-DSA-65 is FIPS 204 (NIST level 3): ~3.3KB signatures, ~2KB public
keys, ~4KB secret keys. Quantum-resistant under the lattice-based
Hardness of Module Learning With Errors.

The dilithium-py package (pure Python, no native deps) provides the
FIPS 204 reference implementation. It's imported lazily so the core
SDK stays lean; install `claudeway[pq]` to enable this backend.

Why a pure-Python backend ships by default: the SignatureBackend ABC is
the moat, not any one crypto. A backend that pip-installs everywhere
(and runs in any CI sandbox) proves the ABC is real and round-trips.
Production users needing native speed can swap in a liboqs-backed
backend against the same ABC.
"""

from __future__ import annotations

from .signing import SignatureBackend


def _load_mldsa65():
    """Lazily import the ML-DSA-65 parameter set or raise a clear error."""
    try:
        from dilithium_py.ml_dsa import ML_DSA_65
    except ImportError as exc:
        raise ImportError(
            "ML-DSA-65 backend requires dilithium-py (FIPS 204). "
            "Install with: pip install claudeway[pq]"
        ) from exc
    return ML_DSA_65


class MLDSABackend(SignatureBackend):
    """
    Post-quantum signature backend. ML-DSA-65 (FIPS 204) over pure Python.

    Same interface as Ed25519Backend: generate_keypair() returns
    (private_key_hex, public_key_hex), sign_receipt()/verify_receipt()
    are inherited from SignatureBackend and work unchanged. Receipts
    signed via this backend self-tag algorithm="mldsa65".

    Signatures are ~3.3KB (vs 64 bytes for Ed25519) — the cost of
    post-quantum security today. Worth it for long-lived attestations
    (M&A diligence records, audit logs) that must stay verifiable
    across the transition to cryptographically relevant quantum
    hardware.
    """

    algorithm = "mldsa65"

    def __init__(self) -> None:
        self._mldsa = _load_mldsa65()

    def generate_keypair(self) -> tuple[str, str]:
        # ML_DSA_65.keygen() returns (pk, sk); SignatureBackend wants (sk, pk).
        pk, sk = self._mldsa.keygen()
        return sk.hex(), pk.hex()

    def _public_from_private(self, private_key_hex: str) -> str:
        return self._mldsa.pk_from_sk(bytes.fromhex(private_key_hex)).hex()

    def sign(self, message: bytes, private_key_hex: str) -> str:
        sk = bytes.fromhex(private_key_hex)
        return self._mldsa.sign(sk, message).hex()

    def verify(self, message: bytes, signature_hex: str, public_key_hex: str) -> bool:
        pk = bytes.fromhex(public_key_hex)
        sig = bytes.fromhex(signature_hex)
        return bool(self._mldsa.verify(pk, message, sig))
