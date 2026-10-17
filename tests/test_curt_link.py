"""
Receipt → .curt linkage: transcripts as evidence, receipts as the decision.

Covers: building conforming .curt transcripts from a consensus round,
linking a receipt to them (refs inside the signed payload), emitting the
receipt as a .curt decision artifact, end-to-end verification, and the
tamper paths (transcript hash mismatch, payload tamper, unlinked receipts).
Structural conformance is checked against the SPEC.md v1 rules — the same
rules schema/curt-v1.schema.json renders non-normatively.
"""

import copy
import json
from unittest.mock import patch

import pytest

from tractum.agent import Agent, AgentConfig
from tractum.consensus import ConsensusResult
from tractum.curt_link import (
    CURT_MAGIC,
    CurtLinkError,
    build_curt_transcript,
    curt_transcript_hash,
    emit_curt_decision,
    link_receipt,
    parse_curt,
    receipt_from_curt_decision,
    transcript_refs,
    validate_curt,
    verify_curt_link,
)
from tractum.signing import (
    CONSENSUS_PAYLOAD_V1,
    CONSENSUS_PAYLOAD_V2,
    ConsensusReceipt,
    Ed25519Backend,
    ReceiptVerification,
    verify_receipt_detailed,
)
from tractum.swarm import AgentResponse, Swarm, SwarmConfig, Task

# --- helpers -----------------------------------------------------------------


def _make_statement(backend: Ed25519Backend, priv: str, agent: str, answer: str):
    statement = {
        "type": "claudeway.agent-statement.v1",
        "swarm": "DBPicker",
        "task_id": "t1",
        "agent": agent,
        "role": "db specialist",
        "model": "claude-test",
        "round": 1,
        "answer": answer,
        "confidence": 0.9,
        "signed_at": "2026-10-01T00:00:00+00:00",
    }
    return backend.sign_statement(statement, priv)


def _result(responses: list[AgentResponse], final: str = "use sqlite") -> ConsensusResult:
    return ConsensusResult(
        final_answer=final, method="weighted_vote",
        agent_count=len(responses), responses=responses,
    )


def _make_linked_receipt(
    agents: tuple[str, ...] = ("A", "B"),
    answer: str = "use sqlite",
):
    """A linked, operator-signed v2 receipt over two evidence transcripts.

    Returns (receipt, transcripts, operator_pub, backend) — evidence is
    split across two .curt files (round 1 / round 2) to exercise multi-file
    linkage.
    """
    backend = Ed25519Backend()
    agent_priv, _ = backend.generate_keypair()
    operator_priv, operator_pub = backend.generate_keypair()

    def response(agent: str, round_num: int) -> AgentResponse:
        return AgentResponse(
            agent_name=agent,
            answer=answer,
            confidence=0.9,
            round=round_num,
            statement=_make_statement(backend, agent_priv, agent, answer),
        )

    transcript1 = build_curt_transcript(
        _result([response(a, 1) for a in agents]), title="round 1"
    )
    transcript2 = build_curt_transcript(
        _result([response(a, 2) for a in agents]), title="round 2"
    )

    receipt = ConsensusReceipt.from_result(
        _result([response(a, 2) for a in agents]),
        swarm_name="DBPicker", task_id="t1",
    )
    receipt = link_receipt(receipt, [transcript1, transcript2])
    backend.sign_receipt(receipt, operator_priv)
    return receipt, [transcript1, transcript2], operator_pub, backend


# --- transcript construction + structural conformance ---


def test_transcript_conforms_to_curt_v1():
    doc = build_curt_transcript(
        _result([AgentResponse(agent_name="A", answer="use sqlite", confidence=0.9)])
    )
    assert validate_curt(doc) == []
    assert doc["curt"] == CURT_MAGIC
    assert doc["version"] == 1
    assert doc["extensions"] == ["agent-context"]
    (message,) = doc["conversation"]["messages"]
    assert message["role"] == "assistant"
    assert message["content"] == "use sqlite"
    assert message["agentId"] == "A"


def test_transcript_id_is_content_addressed_and_stable():
    result = _result([AgentResponse(agent_name="A", answer="x")])
    assert build_curt_transcript(result)["conversation"]["id"] == \
        build_curt_transcript(result)["conversation"]["id"]


def test_message_ids_are_scoped_to_the_full_conversation_id():
    """Regression: message ids once used only the first 12 chars of the
    conversation id, so two transcripts whose content-addressed ids shared
    leading digest chars (1-in-256) collided on message ids and
    emit_curt_decision's dedupe silently dropped real messages."""
    doc1 = build_curt_transcript(
        _result([AgentResponse(agent_name="A", answer="r1", round=1)])
    )
    doc2 = build_curt_transcript(
        _result([AgentResponse(agent_name="A", answer="r2", round=2)])
    )
    assert doc1["conversation"]["id"] != doc2["conversation"]["id"]
    for doc in (doc1, doc2):
        cid = doc["conversation"]["id"]
        for message in doc["conversation"]["messages"]:
            assert message["id"].startswith(f"{cid}-m")
    # Merging both transcripts into one decision file keeps every message.
    receipt = ConsensusReceipt.from_result(
        _result([AgentResponse(agent_name="A", answer="r2", round=2)]),
        swarm_name="s", task_id="t",
    )
    decision = emit_curt_decision(receipt, [doc1, doc2])
    assert len(decision["conversation"]["messages"]) == 2


def test_transcript_hash_survives_tab_indented_serialization():
    doc = build_curt_transcript(_result([AgentResponse(agent_name="A", answer="x")]))
    # The spec's tab-indent writer convention vs any other formatting: the
    # hash is defined over the canonical parsed document, not file bytes.
    tabbed_text = json.dumps(doc, indent="\t", ensure_ascii=False)
    assert curt_transcript_hash(parse_curt(tabbed_text)) == curt_transcript_hash(doc)


def test_parse_curt_strips_one_bom_and_rejects_garbage():
    text = json.dumps(
        build_curt_transcript(_result([AgentResponse(agent_name="A", answer="x")]))
    )
    assert parse_curt("﻿" + text)["version"] == 1
    # At most ONE leading BOM is ignored — a second is body data, and a BOM
    # inside the body is a whole-file rejection.
    with pytest.raises(CurtLinkError):
        parse_curt("﻿" + "﻿" + text)
    with pytest.raises(CurtLinkError):
        parse_curt("{not json")
    with pytest.raises(CurtLinkError):
        parse_curt("[]")


@pytest.mark.parametrize("mutate,problem", [
    (lambda d: d.update(curt="nope"), "curt"),
    (lambda d: d.update(version="1"), "version"),
    (lambda d: d.update(version=True), "version"),
    (lambda d: d["conversation"].update(id=1), "id"),
    (lambda d: d["conversation"].update(createdAt="123"), "createdAt"),
    (lambda d: d["conversation"]["messages"][0].update(role="admin"), "role"),
    (lambda d: d["conversation"]["messages"][0].update(content=5), "content"),
    (lambda d: d["conversation"]["messages"][0].update(timestamp=None), "timestamp"),
])
def test_validate_curt_rejects_spec_violations_whole_file(mutate, problem):
    doc = build_curt_transcript(_result([AgentResponse(agent_name="A", answer="x")]))
    mutate(doc)
    problems = validate_curt(doc)
    assert len(problems) == 1
    assert problem in problems[0]


# --- linkage: refs inside the signed payload ---


def test_link_receipt_embeds_refs_and_resigns():
    receipt, transcripts, operator_pub, _ = _make_linked_receipt()
    refs = receipt.payload["curt"]["transcripts"]
    assert refs == transcript_refs(transcripts)
    assert refs[0]["id"] != refs[1]["id"]
    # The linkage lives INSIDE the signed payload, so the aggregate
    # signature covers it.
    report = verify_receipt_detailed(receipt, expected_operator_pubkey=operator_pub)
    assert report.valid is True
    assert receipt.payload["type"] == CONSENSUS_PAYLOAD_V2


def test_linking_does_not_touch_unlinked_wire_format():
    """The additive guarantee: no .curt features → payload unchanged."""
    receipt = ConsensusReceipt.from_result(
        _result([AgentResponse(agent_name="A", answer="x", confidence=0.5)]),
        swarm_name="s", task_id="t",
    )
    assert "curt" not in receipt.payload
    assert receipt.payload["type"] == CONSENSUS_PAYLOAD_V1


def test_linking_signed_receipt_without_key_is_refused():
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    result = _result([AgentResponse(agent_name="A", answer="x", confidence=0.5)])
    receipt = ConsensusReceipt.from_result(result, swarm_name="s", task_id="t")
    backend.sign_receipt(receipt, priv)
    transcript = build_curt_transcript(result)
    with pytest.raises(CurtLinkError, match="already signed"):
        link_receipt(receipt, transcript)
    # Linking before signing is the normal flow; re-signing right inside
    # link_receipt works too.
    op_priv, _ = backend.generate_keypair()
    relinked = link_receipt(receipt, transcript, private_key_hex=op_priv)
    assert verify_curt_link(relinked, transcript).valid is True


def test_transcript_refs_reject_nonconforming_documents():
    doc = build_curt_transcript(_result([AgentResponse(agent_name="A", answer="x")]))
    doc["version"] = 2
    with pytest.raises(CurtLinkError, match="conforming"):
        transcript_refs([doc])


# --- verification: the full chain ---


def test_linked_receipt_and_transcripts_verify_end_to_end():
    receipt, transcripts, operator_pub, _ = _make_linked_receipt()
    report = verify_curt_link(receipt, transcripts, expected_operator_pubkey=operator_pub)
    assert report.linked is True
    assert report.receipt.valid is True
    assert all(link.valid for link in report.links)
    assert report.links_valid is True
    assert report.valid is True


def test_verify_reuses_the_detailed_receipt_verifier():
    """The receipt half of the verdict IS verify_receipt_detailed's output."""
    receipt, transcripts, _, _ = _make_linked_receipt()
    report = verify_curt_link(receipt, transcripts)
    assert isinstance(report.receipt, ReceiptVerification)
    assert report.receipt == verify_receipt_detailed(receipt)
    assert report.receipt.quorum == 2
    assert report.receipt.valid_statements == 2


# --- tamper detection ---


def test_transcript_hash_mismatch_is_detected():
    receipt, transcripts, operator_pub, _ = _make_linked_receipt()
    tampered = copy.deepcopy(transcripts)
    tampered[1]["conversation"]["messages"][0]["content"] = "use postgres"
    report = verify_curt_link(receipt, tampered, expected_operator_pubkey=operator_pub)
    assert report.receipt.valid is True  # the receipt itself is intact
    assert report.links[0].valid is True
    assert report.links[1].valid is False
    assert report.links[1].reason == "hash-mismatch"
    assert report.valid is False


def test_missing_transcript_is_reported_not_ignored():
    receipt, transcripts, _, _ = _make_linked_receipt()
    report = verify_curt_link(receipt, transcripts[:1])
    assert report.links[0].valid is True
    assert report.links[1].reason == "missing"
    assert report.valid is False


def test_structurally_invalid_transcript_fails_even_on_hash_match():
    receipt, transcripts, _, _ = _make_linked_receipt()
    # Tamper AND re-point the receipt's ref at the tampered doc: the hash
    # now matches, but the doc is no longer a conforming .curt file.
    doctored = copy.deepcopy(transcripts[0])
    doctored["conversation"]["messages"][0]["role"] = "admin"
    receipt.payload["curt"]["transcripts"][0]["sha256"] = curt_transcript_hash(doctored)
    report = verify_curt_link(receipt, [doctored, transcripts[1]])
    assert report.links[0].reason == "invalid-structure"
    assert report.valid is False


def test_swapped_transcript_reference_breaks_verification():
    """Re-pointing a ref at a different transcript fails BOTH linkage and
    the aggregate signature — refs are inside the signed payload."""
    receipt, transcripts, operator_pub, _ = _make_linked_receipt()
    doctored = copy.deepcopy(transcripts[0])
    doctored["conversation"]["id"] = "impostor"
    receipt.payload["curt"]["transcripts"][0] = {
        "id": "impostor", "sha256": curt_transcript_hash(doctored),
    }
    report = verify_curt_link(
        receipt, transcripts + [doctored], expected_operator_pubkey=operator_pub,
    )
    # The payload edit invalidates payload_hash → the aggregate fails first.
    assert report.receipt.aggregate_valid is False
    assert report.valid is False


def test_receipt_payload_tamper_outside_curt_still_caught():
    receipt, transcripts, operator_pub, _ = _make_linked_receipt()
    receipt.payload["result"]["final_answer"] = "use postgres"
    report = verify_curt_link(receipt, transcripts, expected_operator_pubkey=operator_pub)
    assert report.receipt.aggregate_valid is False
    assert report.valid is False


def test_unlinked_receipt_reports_not_linked():
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    result = _result([AgentResponse(agent_name="A", answer="x", confidence=0.5)])
    receipt = ConsensusReceipt.from_result(result, swarm_name="s", task_id="t")
    backend.sign_receipt(receipt, priv)
    report = verify_curt_link(receipt, build_curt_transcript(result))
    assert report.linked is False
    assert report.receipt.valid is True  # v1 semantics intact
    assert report.valid is False  # but the evidence chain does not hold


# --- v1 receipts (no statements) ---


def test_v1_receipt_links_and_verifies():
    backend = Ed25519Backend()
    op_priv, op_pub = backend.generate_keypair()
    result = _result([AgentResponse(agent_name="A", answer="x", confidence=0.5)])
    receipt = ConsensusReceipt.from_result(result, swarm_name="s", task_id="t")
    assert receipt.payload["type"] == CONSENSUS_PAYLOAD_V1
    transcript = build_curt_transcript(result)
    receipt = link_receipt(receipt, transcript)
    # No statements were attached — linking alone must not upgrade the
    # payload type. The type is v1's contract, not the linkage's.
    assert receipt.payload["type"] == CONSENSUS_PAYLOAD_V1
    backend.sign_receipt(receipt, op_priv)
    report = verify_curt_link(receipt, transcript, expected_operator_pubkey=op_pub)
    assert report.valid is True
    assert report.receipt.quorum == 0
    assert report.receipt.quorum_met is True


def test_v1_unlinked_verifies_exactly_as_before():
    """v1 back-compat: the aggregate signature alone decides, no curt key."""
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    receipt = ConsensusReceipt.from_result(
        _result([AgentResponse(agent_name="A", answer="x", confidence=0.5)]),
        swarm_name="s", task_id="t",
    )
    backend.sign_receipt(receipt, priv)
    assert verify_receipt_detailed(receipt).valid is True
    assert "curt" not in receipt.payload


# --- decision artifact: one file, evidence + decision ---


def test_decision_artifact_round_trips_and_verifies():
    receipt, transcripts, operator_pub, _ = _make_linked_receipt()
    decision = emit_curt_decision(receipt, transcripts)
    assert validate_curt(decision) == []
    assert set(decision["extensions"]) == {"agent-context", "consensus-receipt"}
    # Evidence rides in messages; the decision rides in extension fields.
    assert len(decision["conversation"]["messages"]) == 4
    assert "consensusReceipt" in decision["conversation"]

    recovered = receipt_from_curt_decision(decision)
    assert recovered.payload == receipt.payload
    report = verify_curt_link(
        recovered, transcripts, expected_operator_pubkey=operator_pub,
    )
    assert report.valid is True


def test_decision_artifact_from_file_bytes_round_trips():
    receipt, transcripts, operator_pub, _ = _make_linked_receipt()
    decision = emit_curt_decision(receipt, transcripts)
    # The spec's writer convention: UTF-8 JSON, tab-indented, no BOM.
    text = json.dumps(decision, indent="\t", ensure_ascii=False)
    recovered = receipt_from_curt_decision(parse_curt(text))
    assert verify_curt_link(
        recovered, transcripts, expected_operator_pubkey=operator_pub,
    ).valid is True


def test_decision_artifact_refs_must_match_linked_payload():
    receipt, transcripts, _, _ = _make_linked_receipt()
    other = build_curt_transcript(
        _result([AgentResponse(agent_name="Z", answer="y", confidence=0.1)])
    )
    with pytest.raises(CurtLinkError, match="different transcripts"):
        emit_curt_decision(receipt, [transcripts[0], other])


def test_decision_artifact_works_for_unlinked_receipt():
    """emit on an unlinked receipt writes the refs it computed — the .curt
    is still conformant and the receipt inside still verifies on its own."""
    backend = Ed25519Backend()
    op_priv, op_pub = backend.generate_keypair()
    result = _result([AgentResponse(agent_name="A", answer="x", confidence=0.5)])
    receipt = ConsensusReceipt.from_result(result, swarm_name="s", task_id="t")
    backend.sign_receipt(receipt, op_priv)
    transcript = build_curt_transcript(result)
    decision = emit_curt_decision(receipt, transcript)
    assert validate_curt(decision) == []
    recovered = receipt_from_curt_decision(decision)
    assert verify_receipt_detailed(
        recovered, expected_operator_pubkey=op_pub
    ).valid is True


def test_receipt_from_non_decision_document_raises():
    doc = build_curt_transcript(_result([AgentResponse(agent_name="A", answer="x")]))
    with pytest.raises(CurtLinkError, match="decision artifact"):
        receipt_from_curt_decision(doc)


# --- real swarm end to end ---


@pytest.mark.asyncio
async def test_swarm_result_builds_conforming_transcript_and_verifies():
    """A real Swarm (mocked LLM): process → transcript → linked signed
    receipt → verified chain."""
    swarm = Swarm(SwarmConfig(
        name="Demo", description="d",
        agents=[
            AgentConfig("A", "role a", "inst"),
            AgentConfig("B", "role b", "inst"),
        ],
    ), api_key="test-key")

    async def fake_think(self, prompt):
        return "<answer>use sqlite</answer><confidence>0.9</confidence><reasoning>r</reasoning>"

    with patch.object(Agent, "think", fake_think):
        task = await swarm.process(Task(id="t1", description="q", input_data={}))

    responses = task.result["responses"]
    rebuilt = ConsensusResult(
        final_answer=task.result["final_answer"],
        method=task.result["method"],
        agent_count=task.result["agent_count"],
        responses=[
            AgentResponse(
                agent_name=r["agent"], answer=r["answer"], confidence=r["confidence"],
                statement=r.get("statement"),
            )
            for r in responses
        ],
        agreement=task.result["agreement"],
    )
    transcript = build_curt_transcript(rebuilt)
    assert validate_curt(transcript) == []
    receipt = ConsensusReceipt.from_result(rebuilt, swarm_name="Demo", task_id="t1")
    receipt = link_receipt(receipt, transcript)
    backend = Ed25519Backend()
    priv, pub = backend.generate_keypair()
    backend.sign_receipt(receipt, priv)
    report = verify_curt_link(receipt, transcript, expected_operator_pubkey=pub)
    assert report.valid is True
    assert report.receipt.quorum == 2
