"""
Tractum ↔ .curt linkage — receipts as the decision artifact over .curt
transcript evidence.

A quorum receipt (ConsensusReceipt) is the DECISION; the .curt transcript(s)
the consensus was computed from are the EVIDENCE. This module welds the two:

  - build_curt_transcript: turn a ConsensusResult into a conforming .curt v1
    document (SPEC.md validation rules, `agent-context` extension for
    per-message agent provenance).
  - link_receipt: add transcript references (id + sha256) into a receipt
    payload, under the payload key ``curt``. The key only exists when linking
    is used, so untouched receipts stay byte-identical to v0.4.0 wire format.
    Because the refs live INSIDE the signed payload, the aggregate signature
    covers the linkage — a swapped or doctored transcript reference breaks
    verification.
  - emit_curt_decision: emit receipt + evidence as ONE .curt v1 file (the
    `consensus-receipt` extension carries the receipt at conversation level).
  - verify_curt_link: verify the receipt via the existing signing paths
    (verify_receipt_detailed — no crypto reimplemented here) AND the linkage
    (hash match + structural .curt conformance).

Extension note (dot_curt/EXTENSIONS.md): this module emits two extension
names in the top-level ``extensions`` array —

  - ``agent-context`` (registered, draft): per-message ``agentId``.
  - ``consensus-receipt`` (NOT yet in the registry — see the module-level
    docstring block below for its field contract; a registry PR to
    dot_curt/EXTENSIONS.md is pending). Per SPEC.md rule 2, conforming
    readers that don't know an extension ignore it entirely, so emitting it
    is forward-compatible.

The ``consensus-receipt`` extension contract (draft, writer = tractum):

  - Conversation-level ``consensusReceipt``: a full receipt dict
    (ConsensusReceipt.to_dict() shape) — payload, signature envelope,
    payload_hash. Verifiable with tractum.signing paths.
  - Conversation-level ``consensusTranscripts``: array of
    ``{"id": <conversation id>, "sha256": <curt_transcript_hash>}`` — the
    evidence .curt files this decision was computed from. Mirrors the refs
    embedded in the receipt payload under ``curt``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from .consensus import ConsensusResult
from .signing import (
    ConsensusReceipt,
    ReceiptVerification,
    SignatureBackend,
    verify_receipt_detailed,
)

# --- .curt constants (SPEC.md) ------------------------------------------------

CURT_MAGIC = "curtis-conversation"
CURT_VERSION = 1

AGENT_CONTEXT_EXTENSION = "agent-context"
CONSENSUS_RECEIPT_EXTENSION = "consensus-receipt"

_MESSAGE_ROLES = frozenset({"user", "assistant", "system", "tool"})


class CurtLinkError(ValueError):
    """Raised when a .curt linkage request is malformed (not a verify failure)."""


# --- Canonical hashing --------------------------------------------------------


def curt_canonical_json(doc: Any) -> str:
    """
    Deterministic JSON for .curt hashing: sorted keys, compact separators.

    The .curt spec fixes validation, not serialization, so the transcript
    hash is defined over this canonical form — whitespace/indent choices
    (the spec's tab convention vs anything else) never break a linkage.
    """
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def curt_transcript_hash(doc: dict[str, Any]) -> str:
    """sha256 over the canonical form of a parsed .curt document."""
    return hashlib.sha256(curt_canonical_json(doc).encode("utf-8")).hexdigest()


def parse_curt(text: str) -> dict[str, Any]:
    """
    Parse .curt file text into a document dict, per SPEC.md: ignore at most
    one leading UTF-8 BOM, then require a JSON object. Raises CurtLinkError
    on bad JSON or a non-object body (whole-file rejection, never partial).
    """
    if text.startswith("﻿"):
        text = text[1:]
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CurtLinkError(f"not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise CurtLinkError("curt body must be a JSON object")
    return doc


# --- Structural validation (SPEC.md "Validation rules (version 1)") -----------
#
# Hand-rolled instead of the jsonschema dep: schema/curt-v1.schema.json is
# non-normative, and the normative rules are a dozen lines. Booleans are
# rejected where numbers are required (bool is an int subclass in Python —
# `True` must not pass as version/timestamp).


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_curt(doc: Any) -> list[str]:
    """
    Structural checks mirroring SPEC.md version-1 validation rules. Returns a
    list of problems (empty = conforming). Whole-file strictness: any entry
    in the list means reject, never best-effort.
    """
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["top level is not an object"]
    if doc.get("curt") != CURT_MAGIC:
        errors.append('curt must be exactly "curtis-conversation"')
    if not (isinstance(doc.get("version"), int) and not isinstance(doc["version"], bool)
            and doc["version"] == CURT_VERSION):
        errors.append("version must be exactly the number 1")
    ext = doc.get("extensions")
    if ext is not None and not (
        isinstance(ext, list)
        and all(isinstance(e, str) and e for e in ext)
    ):
        # SPEC: writers should emit an array of non-empty strings. Not a
        # validation input for readers, but a writer-side conformance check.
        errors.append("extensions must be an array of non-empty strings")
    conversation = doc.get("conversation")
    if not isinstance(conversation, dict):
        errors.append("conversation must be an object")
        return errors
    for key in ("id", "title"):
        if not isinstance(conversation.get(key), str):
            errors.append(f"conversation.{key} must be a string")
    for key in ("createdAt", "updatedAt"):
        if not _is_number(conversation.get(key)):
            errors.append(f"conversation.{key} must be a number")
    messages = conversation.get("messages")
    if not isinstance(messages, list):
        errors.append("conversation.messages must be an array")
        return errors
    for i, message in enumerate(messages):
        if not isinstance(message, dict):
            errors.append(f"messages[{i}] must be an object")
            continue
        if not isinstance(message.get("id"), str):
            errors.append(f"messages[{i}].id must be a string")
        if message.get("role") not in _MESSAGE_ROLES:
            errors.append(f"messages[{i}].role must be one of user/assistant/system/tool")
        if not isinstance(message.get("content"), str):
            errors.append(f"messages[{i}].content must be a string")
        if not _is_number(message.get("timestamp")):
            errors.append(f"messages[{i}].timestamp must be a number")
    return errors


# --- Evidence: ConsensusResult -> .curt transcript -----------------------------


def _epoch_ms(timestamp: datetime) -> int:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return int(timestamp.astimezone(UTC).timestamp() * 1000)


def _result_messages(result: ConsensusResult, conversation_id: str) -> list[dict[str, Any]]:
    """One assistant message per agent response, `agent-context` provenance."""
    messages: list[dict[str, Any]] = []
    for i, response in enumerate(result.responses):
        content = response.content or response.answer
        messages.append({
            # Scoped to the FULL conversation id so ids stay stable and unique
            # even when several transcripts are merged into one decision
            # file. (A short prefix once collided 1-in-256 on transcripts
            # whose content-addressed ids shared leading digest chars, making
            # emit_curt_decision's id-based dedupe drop real messages.)
            "id": f"{conversation_id}-m{i:03d}",
            "role": "assistant",
            "content": content,
            "timestamp": _epoch_ms(response.timestamp),
            # agent-context extension (draft): multi-agent provenance.
            "agentId": response.agent_name,
            # Writer-defined extra fields; readers preserve, never interpret.
            "confidence": response.confidence,
            "round": response.round,
        })
    return messages


def build_curt_transcript(
    result: ConsensusResult,
    *,
    conversation_id: str = "",
    title: str = "",
) -> dict[str, Any]:
    """
    Build a conforming .curt v1 document from a consensus round's responses
    (the evidence artifact). Extensions declared: ``agent-context``.

    conversation_id: writer's choice of stable id (SPEC.md leaves the scheme
        to the writer). Defaults to a content-addressed id derived from the
        canonical message list, so the same evidence always yields the same
        conversation id (and therefore the same document hash).
    title: human-readable title; defaults to the consensus final answer.
    """
    if not conversation_id:
        # Content-addressed id, computed over the raw response facts (not
        # the message dicts, whose ids embed the conversation id itself).
        facts = [
            [r.agent_name, r.content or r.answer, r.confidence, r.round,
             _epoch_ms(r.timestamp)]
            for r in result.responses
        ]
        digest = hashlib.sha256(curt_canonical_json(facts).encode("utf-8")).hexdigest()
        conversation_id = f"tractum-{digest[:16]}"
    messages = _result_messages(result, conversation_id)
    timestamps = [m["timestamp"] for m in messages] or [0]
    return {
        "curt": CURT_MAGIC,
        "version": CURT_VERSION,
        "generator": "tractum",
        "extensions": [AGENT_CONTEXT_EXTENSION],
        "conversation": {
            "id": conversation_id,
            "title": title or result.final_answer[:80],
            "createdAt": min(timestamps),
            "updatedAt": max(timestamps),
            "messages": messages,
        },
    }


# --- Linkage: receipt payload -> transcript refs -------------------------------


def transcript_refs(transcripts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Reference entries ({id, sha256}) for a list of .curt documents."""
    refs: list[dict[str, str]] = []
    for doc in transcripts:
        errors = validate_curt(doc)
        if errors:
            raise CurtLinkError(
                f"transcript {doc.get('conversation', {}).get('id', '?')!r} "
                f"is not a conforming .curt v1 document: {'; '.join(errors)}"
            )
        refs.append({
            "id": doc["conversation"]["id"],
            "sha256": curt_transcript_hash(doc),
        })
    return refs


def link_receipt(
    receipt: ConsensusReceipt,
    transcripts: list[dict[str, Any]] | dict[str, Any],
    *,
    backend: SignatureBackend | None = None,
    private_key_hex: str = "",
) -> ConsensusReceipt:
    """
    Return a COPY of the receipt whose payload references the given .curt
    transcripts, under the payload key ``curt``:

        "curt": {"transcripts": [{"id": ..., "sha256": ...}, ...]}

    The payload hash is recomputed. If the receipt is already signed, the
    signature no longer covers the new payload — pass private_key_hex (and
    optionally a backend; default Ed25519) to re-sign here, or raise:
    linking a signed receipt without a key is refused rather than left
    silently unverifiable. Receipts not yet signed (the normal flow:
    from_result -> link_receipt -> sign_receipt) pass through with their
    signature fields untouched.

    Wire format: the ``curt`` key only exists when linking is used. Without
    it, payloads are byte-identical to the pre-linkage format.
    """
    docs = [transcripts] if isinstance(transcripts, dict) else list(transcripts)
    if not docs:
        raise CurtLinkError("link_receipt requires at least one transcript")
    if receipt.is_signed and not private_key_hex:
        raise CurtLinkError(
            "receipt is already signed; re-sign with private_key_hex or link "
            "before signing (the old signature cannot cover the new payload)"
        )
    payload = dict(receipt.payload)
    payload["curt"] = {"transcripts": transcript_refs(docs)}
    linked = replace(receipt, payload=payload)
    linked.payload_hash = hashlib.sha256(
        linked.canonical_payload().encode("utf-8")
    ).hexdigest()
    if private_key_hex:
        (backend or _default_backend()).sign_receipt(linked, private_key_hex)
    return linked


# --- Decision artifact: receipt + evidence as one .curt file -------------------


def emit_curt_decision(
    receipt: ConsensusReceipt,
    transcripts: list[dict[str, Any]] | dict[str, Any],
    *,
    conversation_id: str = "",
    title: str = "",
) -> dict[str, Any]:
    """
    Emit the receipt AS a .curt-conformant artifact: one file whose messages
    are the evidence transcript and whose `consensus-receipt` extension
    fields carry the decision (the full receipt dict + transcript refs).

    The receipt must already be linked (link_receipt) and the refs in its
    signed payload must match the transcripts given here — a mismatch means
    the file would carry a decision over different evidence than it embeds,
    so this raises instead of writing a self-contradicting artifact.
    """
    docs = [transcripts] if isinstance(transcripts, dict) else list(transcripts)
    refs = transcript_refs(docs)
    payload_refs = receipt.payload.get("curt", {}).get("transcripts")
    if payload_refs is not None and payload_refs != refs:
        raise CurtLinkError(
            "receipt payload references different transcripts than supplied; "
            "link_receipt the receipt against these transcripts first"
        )

    messages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for doc in docs:
        for message in doc["conversation"]["messages"]:
            mid = message["id"]
            if mid in seen:
                continue
            seen.add(mid)
            messages.append(message)
    timestamps = [m["timestamp"] for m in messages] or [0]
    if not conversation_id:
        first = refs[0]["id"] if refs else "decision"
        conversation_id = f"{first}-decision"
    return {
        "curt": CURT_MAGIC,
        "version": CURT_VERSION,
        "generator": "tractum",
        "extensions": [AGENT_CONTEXT_EXTENSION, CONSENSUS_RECEIPT_EXTENSION],
        "conversation": {
            "id": conversation_id,
            "title": title or receipt.payload.get("swarm", "Consensus decision"),
            "createdAt": min(timestamps),
            "updatedAt": max(timestamps),
            "messages": messages,
            # consensus-receipt extension (conversation level):
            "consensusReceipt": receipt.to_dict(),
            "consensusTranscripts": refs,
        },
    }


def receipt_from_curt_decision(doc: dict[str, Any]) -> ConsensusReceipt:
    """
    Recover the receipt embedded in a decision artifact's
    ``consensusReceipt`` extension field. Raises CurtLinkError if absent.
    """
    conversation = doc.get("conversation")
    if not isinstance(conversation, dict) or "consensusReceipt" not in conversation:
        raise CurtLinkError("not a consensus-receipt decision artifact")
    data = conversation["consensusReceipt"]
    return ConsensusReceipt(
        payload=data.get("payload", {}),
        algorithm=data.get("algorithm", ""),
        public_key=data.get("public_key", ""),
        signature=data.get("signature", ""),
        payload_hash=data.get("payload_hash", ""),
        signed_at=data.get("signed_at", ""),
        metadata=data.get("metadata", {}),
    )


# --- Verification ---------------------------------------------------------------


@dataclass
class TranscriptLink:
    """Per-transcript line item of a linkage verification."""

    id: str
    expected_hash: str
    actual_hash: str
    structure_errors: list[str] = field(default_factory=list)
    valid: bool = False
    reason: str = ""  # "" when valid; else missing / hash-mismatch / ...


@dataclass
class CurtLinkVerification:
    """Full verification outcome for a receipt + its .curt evidence."""

    receipt: ReceiptVerification
    links: list[TranscriptLink]
    linked: bool  # payload declared transcript refs at all

    @property
    def links_valid(self) -> bool:
        return self.linked and all(link.valid for link in self.links)

    @property
    def valid(self) -> bool:
        return self.receipt.valid and self.links_valid


def receipt_refs(receipt: ConsensusReceipt) -> list[dict[str, Any]]:
    """The transcript refs a receipt payload declares ([] when unlinked)."""
    refs = receipt.payload.get("curt", {}).get("transcripts", [])
    return list(refs) if isinstance(refs, list) else []


def verify_curt_link(
    receipt: ConsensusReceipt,
    transcripts: list[dict[str, Any]] | dict[str, Any],
    *,
    expected_operator_pubkey: str = "",
    expected_agent_pubkeys: dict[str, str] | None = None,
) -> CurtLinkVerification:
    """
    Verify a linked receipt end to end.

    1. Receipt: delegated to signing.verify_receipt_detailed (aggregate
       signature, per-agent statements, quorum — the existing crypto paths,
       not reimplemented). Because the ``curt`` refs live inside the signed
       payload, any tampering with the linkage already fails here.
    2. Linkage: every ref declared in the payload must be satisfied by a
       supplied transcript with the same conversation id AND the same
       canonical sha256, and every supplied transcript must pass the
       SPEC.md v1 structural rules.
    3. Unlinked receipts (no ``curt`` key) report a single failed link with
       reason "not-linked" rather than pretending the chain holds.
    """
    docs = [transcripts] if isinstance(transcripts, dict) else list(transcripts)
    by_id = {
        doc["conversation"]["id"]: doc
        for doc in docs
        if isinstance(doc, dict)
        and isinstance(doc.get("conversation"), dict)
        and isinstance(doc["conversation"].get("id"), str)
    }

    declared = receipt_refs(receipt)
    if not declared:
        links = [TranscriptLink(
            id="", expected_hash="", actual_hash="", reason="not-linked",
        )]
    else:
        links = []
        for ref in declared:
            ref_id = ref.get("id", "") if isinstance(ref, dict) else ""
            expected = ref.get("sha256", "") if isinstance(ref, dict) else ""
            doc = by_id.get(ref_id)
            if doc is None:
                links.append(TranscriptLink(
                    id=ref_id, expected_hash=expected, actual_hash="",
                    reason="missing",
                ))
                continue
            actual = curt_transcript_hash(doc)
            structure_errors = validate_curt(doc)
            if expected != actual:
                links.append(TranscriptLink(
                    id=ref_id, expected_hash=expected, actual_hash=actual,
                    structure_errors=structure_errors, reason="hash-mismatch",
                ))
            elif structure_errors:
                links.append(TranscriptLink(
                    id=ref_id, expected_hash=expected, actual_hash=actual,
                    structure_errors=structure_errors, reason="invalid-structure",
                ))
            else:
                links.append(TranscriptLink(
                    id=ref_id, expected_hash=expected, actual_hash=actual, valid=True,
                ))

    return CurtLinkVerification(
        receipt=verify_receipt_detailed(
            receipt,
            expected_operator_pubkey=expected_operator_pubkey,
            expected_agent_pubkeys=expected_agent_pubkeys,
        ),
        links=links,
        linked=bool(declared),
    )


def _default_backend() -> SignatureBackend:
    # Local import keeps curt_link free of backend selection policy
    # duplication while matching signing.default_backend().
    from .signing import default_backend

    return default_backend()
