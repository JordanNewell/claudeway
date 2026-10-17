"""
Per-agent statement signing + k-of-n quorum receipts.

The upgrade from "operator says the agents agreed" to "each agent signed its
own stance, and you can count the signatures." Covers: statement sign/verify,
swarm provisioning (ephemeral + pinned keys), v2 receipt assembly, the
detailed verifier (aggregate + statements + quorum), and the v1 back-compat
path. Attack-side tests live in test_adversarial.py.
"""

import hashlib
from unittest.mock import patch

import pytest

from tractum.agent import Agent, AgentConfig
from tractum.consensus import ConsensusResult
from tractum.signing import (
    AGENT_STATEMENT_TYPE,
    CONSENSUS_PAYLOAD_V1,
    CONSENSUS_PAYLOAD_V2,
    ConsensusReceipt,
    Ed25519Backend,
    sign_statement,
    statement_hash,
    verify_receipt_detailed,
    verify_statement,
)
from tractum.signing_pq import MLDSABackend
from tractum.swarm import AgentResponse, Swarm, SwarmConfig

try:
    MLDSABackend()  # dilithium-py is imported lazily — probe it for real.
    HAS_PQ = True
except ImportError:
    HAS_PQ = False


# --- helpers -----------------------------------------------------------------


def _make_statement(
    backend: Ed25519Backend,
    priv: str,
    agent: str = "A",
    answer: str = "use sqlite",
    task_id: str = "t1",
    round_num: int = 1,
) -> dict:
    """A signed statement over a controlled stance."""
    statement = {
        "type": AGENT_STATEMENT_TYPE,
        "swarm": "DBPicker",
        "task_id": task_id,
        "agent": agent,
        "role": "db specialist",
        "model": "claude-test",
        "round": round_num,
        "answer": answer,
        "confidence": 0.9,
        "signed_at": "2026-10-01T00:00:00+00:00",
    }
    return backend.sign_statement(statement, priv)


def _make_receipt(
    statements: list[dict],
    *,
    task_id: str = "t1",
    quorum: int | None = None,
) -> ConsensusReceipt:
    """An unsigned v2 receipt over responses matching the given statements."""
    responses = [
        AgentResponse(
            agent_name=s["agent"],
            answer=s["answer"],
            confidence=s["confidence"],
            round=s.get("round", 1),
            statement=s,
        )
        for s in statements
    ]
    result = ConsensusResult(
        final_answer=statements[0]["answer"] if statements else "x",
        method="weighted_vote",
        agent_count=len(responses),
        responses=responses,
        agreement=0.9,
    )
    return ConsensusReceipt.from_result(
        result, swarm_name="DBPicker", task_id=task_id, quorum=quorum
    )


# --- statement sign / verify round trip ---


def test_statement_round_trip():
    backend = Ed25519Backend()
    priv, pub = backend.generate_keypair()
    signed = _make_statement(backend, priv)
    assert signed["algorithm"] == "ed25519"
    assert signed["public_key"] == pub
    assert verify_statement(signed) is True
    assert Ed25519Backend().verify_statement(signed) is True


def test_statement_hash_covers_content_not_envelope():
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    signed = _make_statement(backend, priv)
    # statement_hash is derived from content alone — flipping any envelope
    # field can't hide a content change, and the hash recomputes the same.
    assert statement_hash(signed) == signed["statement_hash"]
    rotated = dict(signed, signature="ff" * 32)
    assert statement_hash(rotated) == signed["statement_hash"]


def test_statement_content_tamper_invalidates():
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    signed = _make_statement(backend, priv)
    signed["answer"] = "use postgres"
    assert verify_statement(signed) is False


def test_statement_hash_tamper_invalidates():
    """Re-deriving the hash catches a doctored statement_hash field."""
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    signed = _make_statement(backend, priv)
    signed["statement_hash"] = "0" * 64
    assert verify_statement(signed) is False


def test_statement_missing_signature_is_unsigned_not_error():
    statement = {
        "type": AGENT_STATEMENT_TYPE, "agent": "A", "answer": "x",
        "confidence": 0.5, "round": 1,
    }
    assert verify_statement(statement) is False


def test_module_level_helpers_use_default_backend():
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    signed = sign_statement({"agent": "A", "answer": "x", "confidence": 0.5}, priv)
    assert signed["algorithm"] == "ed25519"
    assert verify_statement(signed) is True


# --- swarm provisioning + signing ---


@pytest.mark.asyncio
async def test_swarm_signs_every_agent_response():
    """A real Swarm (mocked LLM) attaches one valid statement per response."""
    swarm = Swarm(SwarmConfig(
        name="Demo", description="d",
        agents=[
            AgentConfig("A", "role a", "inst"),
            AgentConfig("B", "role b", "inst"),
        ],
    ), api_key="test-key")

    async def fake_think(self, prompt):
        return "<answer>use sqlite</answer><confidence>0.9</confidence><reasoning>r</reasoning>"

    from tractum.swarm import Task
    with patch.object(Agent, "think", fake_think):
        task = await swarm.process(Task(id="t1", description="q", input_data={}))

    responses = task.result["responses"]
    assert len(responses) == 2
    for r in responses:
        assert r["statement"]["agent"] == r["agent"]
        assert r["statement"]["answer"] == r["answer"]
        assert verify_statement(r["statement"]) is True
    # Distinct agents must not share a signing key.
    pubs = {r["statement"]["public_key"] for r in responses}
    assert len(pubs) == 2


def test_swarm_provisions_ephemeral_keys_when_unpinned():
    swarm = Swarm(SwarmConfig(
        name="Demo", description="d",
        agents=[AgentConfig("A", "role", "inst"), AgentConfig("B", "role", "inst")],
    ), api_key="test-key")
    (_, pub_a), (_, pub_b) = swarm._agent_keys["A"], swarm._agent_keys["B"]
    assert pub_a != pub_b


def test_swarm_honors_pinned_signing_keys():
    backend = Ed25519Backend()
    pinned_priv, pinned_pub = backend.generate_keypair()
    swarm = Swarm(SwarmConfig(
        name="Demo", description="d",
        agents=[AgentConfig("A", "role", "inst", signing_key=pinned_priv)],
    ), api_key="test-key")
    assert swarm._agent_keys["A"][1] == pinned_pub


# --- receipt assembly: v1 vs v2 ---


def test_receipt_without_statements_stays_v1():
    result = ConsensusResult(
        final_answer="x", method="weighted_vote", agent_count=1,
        responses=[AgentResponse(agent_name="A", answer="x", confidence=0.5)],
    )
    receipt = ConsensusReceipt.from_result(result)
    assert receipt.payload["type"] == CONSENSUS_PAYLOAD_V1
    assert "statements" not in receipt.payload
    assert "quorum" not in receipt.payload


def test_receipt_with_statements_is_v2_with_unanimous_quorum_default():
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    statements = [
        _make_statement(backend, priv, agent="A"),
        _make_statement(backend, priv, agent="B", answer="use sqlite"),
    ]
    receipt = _make_receipt(statements)
    assert receipt.payload["type"] == CONSENSUS_PAYLOAD_V2
    assert receipt.payload["quorum"] == 2
    assert receipt.payload["statements"] == statements


def test_receipt_gathers_statements_from_responses():
    """from_result with no explicit statements pulls them off the responses."""
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    statement = _make_statement(backend, priv)
    result = ConsensusResult(
        final_answer="use sqlite", method="weighted_vote", agent_count=1,
        responses=[AgentResponse(
            agent_name="A", answer="use sqlite", confidence=0.9, statement=statement,
        )],
    )
    receipt = ConsensusReceipt.from_result(result, task_id="t1")
    assert receipt.payload["type"] == CONSENSUS_PAYLOAD_V2
    assert receipt.payload["statements"] == [statement]


def test_receipt_survives_dict_round_trip_with_statements():
    """task.result dict → rebuilt responses → v2 receipt still fully valid."""
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    statement = _make_statement(backend, priv)
    response = AgentResponse(
        agent_name="A", answer="use sqlite", confidence=0.9, statement=statement,
    )
    # Simulate the dict round-trip every real swarm result takes.
    result_dict = ConsensusResult(
        final_answer="use sqlite", method="weighted_vote", agent_count=1,
        responses=[response],
    ).to_dict()
    rebuilt = ConsensusResult(
        final_answer=result_dict["final_answer"],
        method=result_dict["method"],
        agent_count=result_dict["agent_count"],
        responses=[
            AgentResponse(
                agent_name=r["agent"], answer=r["answer"],
                confidence=r["confidence"], statement=r.get("statement"),
            )
            for r in result_dict["responses"]
        ],
        agreement=result_dict["agreement"],
    )
    receipt = ConsensusReceipt.from_result(rebuilt, task_id="t1")
    assert receipt.payload["statements"] == [statement]
    backend.sign_receipt(receipt, priv)
    assert verify_receipt_detailed(receipt).valid is True


# --- detailed verification: quorum semantics ---


def test_unanimous_receipt_verifies_fully():
    backend = Ed25519Backend()
    agent_priv, _ = backend.generate_keypair()
    operator_priv, operator_pub = backend.generate_keypair()
    statements = [_make_statement(backend, agent_priv, agent=n) for n in "ABC"]
    receipt = _make_receipt(statements)
    backend.sign_receipt(receipt, operator_priv)
    report = verify_receipt_detailed(receipt, expected_operator_pubkey=operator_pub)
    assert report.valid is True
    assert report.aggregate_valid is True
    assert report.quorum == 3
    assert report.valid_statements == 3
    assert report.total_statements == 3
    assert report.quorum_met is True


def test_quorum_met_when_k_of_n_valid():
    """3 statements, 1 forged, k=2: quorum holds, forgery is named."""
    backend = Ed25519Backend()
    agent_priv, agent_pub = backend.generate_keypair()
    operator_priv, _ = backend.generate_keypair()
    statements = [
        _make_statement(backend, agent_priv, agent="A"),
        _make_statement(backend, agent_priv, agent="B"),
        _make_statement(backend, agent_priv, agent="C"),
    ]
    # Forge C: self-consistent crypto, but signed under a key the verifier
    # doesn't know as C's. Only per-agent pinning catches this.
    forger_priv, _ = backend.generate_keypair()
    statements[2] = _make_statement(backend, forger_priv, agent="C")
    receipt = _make_receipt(statements, quorum=2)
    backend.sign_receipt(receipt, operator_priv)
    known_keys = {a: agent_pub for a in "ABC"}
    report = verify_receipt_detailed(receipt, expected_agent_pubkeys=known_keys)
    assert report.aggregate_valid is True
    assert report.valid_statements == 2
    assert report.quorum_met is True
    assert report.valid is True
    assert report.statements[2].valid is False
    assert report.statements[2].reason == "key-mismatch"


def test_quorum_unmet_when_forgery_drops_valid_count_below_k():
    backend = Ed25519Backend()
    agent_priv, agent_pub = backend.generate_keypair()
    operator_priv, _ = backend.generate_keypair()
    statements = [
        _make_statement(backend, agent_priv, agent="A"),
        _make_statement(backend, agent_priv, agent="B"),
        _make_statement(backend, agent_priv, agent="C"),
    ]
    forger_priv, _ = backend.generate_keypair()
    statements[2] = _make_statement(backend, forger_priv, agent="C")
    receipt = _make_receipt(statements, quorum=3)  # unanimous
    backend.sign_receipt(receipt, operator_priv)
    known_keys = {a: agent_pub for a in "ABC"}
    report = verify_receipt_detailed(receipt, expected_agent_pubkeys=known_keys)
    assert report.valid_statements == 2
    assert report.quorum_met is False
    assert report.valid is False


def test_v1_receipt_verifies_on_aggregate_alone():
    """v1 semantics preserved: no statements, no quorum, aggregate decides."""
    result = ConsensusResult(
        final_answer="x", method="m", agent_count=1,
        responses=[AgentResponse(agent_name="A", answer="x", confidence=0.5)],
    )
    receipt = ConsensusReceipt.from_result(result)
    backend = Ed25519Backend()
    priv, _ = backend.generate_keypair()
    backend.sign_receipt(receipt, priv)
    report = verify_receipt_detailed(receipt)
    assert report.valid is True
    assert report.statements == []
    assert report.quorum == 0
    assert report.quorum_met is True


def test_expected_operator_pubkey_pins_the_verdict():
    """Without pinning, an attacker's fully re-signed forgery verifies."""
    backend = Ed25519Backend()
    agent_priv, _ = backend.generate_keypair()
    operator_priv, operator_pub = backend.generate_keypair()
    statements = [_make_statement(backend, agent_priv, agent="A")]
    receipt = _make_receipt(statements)

    # Attacker: swap the statement and the answer, recompute the hash,
    # re-sign everything with their own key. Self-consistent — the only
    # defense is the verifier pinning the operator key it expects.
    _, attacker = backend.generate_keypair()
    forged = [_make_statement(backend, attacker, agent="A", answer="use postgres")]
    receipt.payload["statements"] = forged
    receipt.payload["result"]["responses"][0]["answer"] = "use postgres"
    receipt.payload_hash = hashlib.sha256(
        receipt.canonical_payload().encode("utf-8")
    ).hexdigest()
    backend.sign_receipt(receipt, attacker)

    unpinned = verify_receipt_detailed(receipt)
    assert unpinned.valid is True  # self-consistent forgery
    pinned = verify_receipt_detailed(receipt, expected_operator_pubkey=operator_pub)
    assert pinned.valid is False


# --- mixed-algorithm statements (post-quantum agent) ---


@pytest.mark.skipif(not HAS_PQ, reason="dilithium-py not installed")
def test_mixed_ed25519_and_mldsa_statements_verify():
    """One agent signs post-quantum; the verifier dispatches per statement."""
    ed = Ed25519Backend()
    ed_priv, _ = ed.generate_keypair()
    pq = MLDSABackend()
    pq_priv, _ = pq.generate_keypair()

    statements = [
        _make_statement(ed, ed_priv, agent="A"),
        pq.sign_statement({
            "type": AGENT_STATEMENT_TYPE, "swarm": "DBPicker", "task_id": "t1",
            "agent": "B", "role": "db specialist", "model": "claude-test",
            "round": 1, "answer": "use sqlite", "confidence": 0.9,
            "signed_at": "2026-10-01T00:00:00+00:00",
        }, pq_priv),
    ]
    receipt = _make_receipt(statements)
    ed_priv_op, _ = ed.generate_keypair()
    ed.sign_receipt(receipt, ed_priv_op)
    report = verify_receipt_detailed(receipt)
    assert report.valid is True
    assert report.valid_statements == 2
