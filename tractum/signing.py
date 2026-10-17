"""
Tractum signing - verifiable, tamper-evident consensus receipts.

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


# --- Payload types -----------------------------------------------------------

# v1: consensus facts only. v2 adds per-agent signed statements + a quorum
# threshold. v1 receipts remain valid forever; the verifier handles both.
CONSENSUS_PAYLOAD_V1 = "claudeway.consensus.v1"
CONSENSUS_PAYLOAD_V2 = "claudeway.consensus.v2"
AGENT_STATEMENT_TYPE = "claudeway.agent-statement.v1"

# Keys added by sign_statement; everything else in a statement dict is signed
# content. Verifiers hash/verify over the content keys only, so any future
# content field is automatically covered by the signature.
_STATEMENT_ENVELOPE_KEYS = frozenset(
    {"algorithm", "public_key", "signature", "statement_hash"}
)


def statement_content(statement: dict[str, Any]) -> dict[str, Any]:
    """The signed portion of a statement dict (envelope keys stripped)."""
    return {k: v for k, v in statement.items() if k not in _STATEMENT_ENVELOPE_KEYS}


def statement_hash(statement: dict[str, Any]) -> str:
    """sha256 over the canonical form of a statement's signed content."""
    canonical = canonical_json(statement_content(statement))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Receipt -----------------------------------------------------------------


@dataclass
class ConsensusReceipt:
    """
    A signed (or signable) consensus attestation.

    payload: the canonical consensus facts (answer, agents, agreement...).
        v1 payloads carry the result only. v2 payloads additionally carry
        per-agent signed statements and the quorum threshold k — the
        aggregate signature then covers the agent signatures too.
    algorithm: which SignatureBackend produced the aggregate signature.
    public_key: hex-encoded verification key of the (operator) signer.
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
        statements: list[dict[str, Any]] | None = None,
        quorum: int | None = None,
    ) -> ConsensusReceipt:
        """
        Build an unsigned receipt from a ConsensusResult.

        statements: per-agent signed statements (dicts as produced by
            SignatureBackend.sign_statement). When omitted, they are
            gathered from the responses themselves (AgentResponse.statement).
            A receipt carrying statements is a v2 payload; without them it
            stays v1 (byte-identical to the original format).
        quorum: how many valid agent statements a verifier must find (k of
            n). Defaults to len(statements) — unanimous. The threshold is
            part of the signed payload, so it can't be downgraded post-hoc.
        """
        if statements is None:
            statements = _statements_from_result(result)
        payload: dict[str, Any] = {
            "type": CONSENSUS_PAYLOAD_V1,
            "swarm": swarm_name,
            "task_id": task_id,
            "result": result.to_dict(),
        }
        if statements:
            payload["type"] = CONSENSUS_PAYLOAD_V2
            payload["quorum"] = len(statements) if quorum is None else quorum
            payload["statements"] = list(statements)
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

    # Convenience: sign/verify one agent statement.

    def sign_statement(
        self, statement: dict[str, Any], private_key_hex: str
    ) -> dict[str, Any]:
        """
        Sign one agent's stance in place and return the signed dict.

        The signature covers the statement's content keys (everything except
        the envelope keys this method fills in). The statement_hash is
        derived, not trusted, so a doctored content field is detectable
        without the key.
        """
        signed = dict(statement)
        message = canonical_json(statement_content(signed)).encode("utf-8")
        signed["statement_hash"] = hashlib.sha256(message).hexdigest()
        signed["algorithm"] = self.algorithm
        signed["public_key"] = self._public_from_private(private_key_hex)
        signed["signature"] = self.sign(message, private_key_hex)
        return signed

    def verify_statement(self, statement: dict[str, Any]) -> bool:
        """Verify one agent statement. Unsigned or tampered statements return False."""
        if not statement.get("signature") or not statement.get("public_key"):
            return False
        recomputed = statement_hash(statement)
        if recomputed != statement.get("statement_hash"):
            return False
        message = canonical_json(statement_content(statement)).encode("utf-8")
        try:
            return self.verify(
                message, statement["signature"], statement["public_key"]
            )
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


# --- Detailed verification ---------------------------------------------------
#
# verify_receipt (above) checks the operator's aggregate signature only. That
# proves the payload wasn't tampered with — not that the agents ever said
# what the payload claims. verify_receipt_detailed additionally checks every
# per-agent statement signature and the quorum threshold, which is what makes
# a v2 receipt a k-of-n attestation rather than one operator's claim.


@dataclass
class StatementVerification:
    """Per-agent line item of a receipt verification."""

    agent: str
    valid: bool
    reason: str = ""  # "" when valid; else signature-invalid / hash-mismatch / ...


@dataclass
class ReceiptVerification:
    """Full verification outcome for a receipt (v1 or v2)."""

    aggregate_valid: bool
    statements: list[StatementVerification]
    quorum: int  # required k (0 for v1 receipts — no quorum semantics)
    valid_statements: int
    total_statements: int

    @property
    def quorum_met(self) -> bool:
        if not self.statements:
            # v1 receipt (or unsigned v2): nothing to count; the aggregate
            # signature alone decides.
            return True
        return self.valid_statements >= self.quorum

    @property
    def valid(self) -> bool:
        return self.aggregate_valid and self.quorum_met


def _backend_for_algorithm(algorithm: str) -> SignatureBackend | None:
    """Resolve a verifier for a statement/receipt algorithm, or None."""
    if algorithm == "ed25519":
        return Ed25519Backend()
    if algorithm == "mldsa65":
        # Lazy: [pq] extra is optional. An uninstalled backend means that
        # statement/receipt can't be verified HERE — reported, not crashed on.
        try:
            from .signing_pq import MLDSABackend

            return MLDSABackend()
        except ImportError:
            return None
    return None


def _statements_from_result(result: ConsensusResult) -> list[dict[str, Any]]:
    """Gather signed statements attached to a result's responses."""
    statements: list[dict[str, Any]] = []
    for r in result.responses:
        if isinstance(r, dict):
            stmt = r.get("statement")
        else:
            stmt = getattr(r, "statement", None)
        if stmt:
            statements.append(stmt)
    return statements


def _check_statement_against_responses(
    statement: dict[str, Any], responses: list[dict[str, Any]]
) -> str:
    """Cross-check a statement against the response it claims to attest.

    Returns "" if consistent, else the failure reason. The statement must
    match the response attributed to the same agent — this is what stops a
    valid statement for answer X being recycled as the attestation for
    answer Y. Statements without a matching response (agent failed, or
    peer-visibility round) are their own evidence and pass this check.
    """
    agent = statement.get("agent", "")
    matches = [r for r in responses if r.get("agent") == agent]
    if not matches:
        return ""
    response = matches[0]
    for key in ("answer", "confidence", "round"):
        if key in statement and key in response:
            if statement[key] != response[key]:
                return f"response-mismatch:{key}"
    return ""


def verify_receipt_detailed(
    receipt: ConsensusReceipt,
    expected_operator_pubkey: str = "",
    expected_agent_pubkeys: dict[str, str] | None = None,
) -> ReceiptVerification:
    """
    Verify a receipt end to end and report exactly what held.

    Checks, in order:
      1. payload_hash matches the payload (tamper guard).
      2. the operator's aggregate signature (under receipt.algorithm).
      3. if expected_operator_pubkey is given: the receipt must be signed by
         THAT key. Without pinning, anyone can re-sign a doctored payload
         with their own key and it would verify "valid" — pinning is what
         makes verification mean something.
      4. every per-agent statement: hash, signature, and consistency with
         the response it claims to attest. If expected_agent_pubkeys maps
         agent names to keys, each statement must be signed by the agent's
         known key — without it, a malicious operator can fabricate
         statements under fresh keys and signature validity alone won't
         catch it (a signature proves self-consistency, not identity).
      5. quorum: valid statements >= k.

    v1 receipts (no statements) verify on the aggregate signature alone,
    preserving the original semantics.
    """
    statements_in_payload = receipt.payload.get("statements", [])
    responses = receipt.payload.get("result", {}).get("responses", [])

    aggregate_valid = False
    if receipt.is_signed:
        recomputed = hashlib.sha256(receipt.canonical_payload().encode("utf-8"))
        hash_ok = recomputed.hexdigest() == receipt.payload_hash
        backend = _backend_for_algorithm(receipt.algorithm)
        if hash_ok and backend is not None:
            message = receipt.canonical_payload().encode("utf-8")
            try:
                aggregate_valid = backend.verify(
                    message, receipt.signature, receipt.public_key
                )
            except Exception:
                aggregate_valid = False
        if expected_operator_pubkey and receipt.public_key != expected_operator_pubkey:
            aggregate_valid = False

    results: list[StatementVerification] = []
    for stmt in statements_in_payload:
        agent = stmt.get("agent", "")
        # A statement pinned to task X is worthless inside a receipt for
        # task Y — replaying signed stances across tasks must not verify.
        # (Revision-round statements carry task_id "" and skip this check.)
        stmt_task = stmt.get("task_id", "")
        if stmt_task and stmt_task != receipt.payload.get("task_id", ""):
            results.append(StatementVerification(
                agent=agent, valid=False, reason="task-id-mismatch",
            ))
            continue
        if (
            expected_agent_pubkeys
            and agent in expected_agent_pubkeys
            and stmt.get("public_key") != expected_agent_pubkeys[agent]
        ):
            results.append(StatementVerification(
                agent=agent, valid=False, reason="key-mismatch",
            ))
            continue
        backend = _backend_for_algorithm(stmt.get("algorithm", ""))
        if backend is None:
            results.append(StatementVerification(
                agent=agent, valid=False,
                reason=f"no-backend:{stmt.get('algorithm', '?')}",
            ))
            continue
        if not backend.verify_statement(stmt):
            reason = (
                "hash-mismatch"
                if statement_hash(stmt) != stmt.get("statement_hash")
                else "signature-invalid"
            )
            results.append(StatementVerification(
                agent=agent, valid=False, reason=reason,
            ))
            continue
        mismatch = _check_statement_against_responses(stmt, responses)
        results.append(StatementVerification(agent=agent, valid=not mismatch, reason=mismatch))

    valid_count = sum(1 for r in results if r.valid)
    return ReceiptVerification(
        aggregate_valid=aggregate_valid,
        statements=results,
        quorum=receipt.payload.get("quorum", 0),
        valid_statements=valid_count,
        total_statements=len(statements_in_payload),
    )


# --- Default backend helper --------------------------------------------------


def default_backend() -> SignatureBackend:
    """The backend used when callers don't specify one."""
    return Ed25519Backend()


# --- Module-level statement helpers ------------------------------------------
#
# Convenience wrappers for the common case (Ed25519 statements). Custom
# backends: call the methods on the backend instance directly.


def sign_statement(
    statement: dict[str, Any],
    private_key_hex: str,
    backend: SignatureBackend | None = None,
) -> dict[str, Any]:
    """Sign one agent statement in place and return the signed dict."""
    return (backend or default_backend()).sign_statement(statement, private_key_hex)


def verify_statement(statement: dict[str, Any]) -> bool:
    """Verify one agent statement's signature and hash. False if tampered."""
    backend = _backend_for_algorithm(statement.get("algorithm", ""))
    if backend is None:
        return False
    return backend.verify_statement(statement)
