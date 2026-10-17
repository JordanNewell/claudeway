"""
MCP server tool behavior: the signing-key policy (pinned vs ephemeral), the
require-pinned guard, dry-run mode, and per-agent pubkey pinning on
verify_consensus. Tool paths run through the real FastMCP server (requires
the [mcp] extra); the pure dry-run helper is tested everywhere.
"""

import json

import pytest

from tractum.agent import AgentConfig
from tractum.server import (
    DRY_RUN_ENV,
    DRY_RUN_SWARM_NAME,
    REQUIRE_PINNED_KEY_ENV,
    SIGNING_KEY_ENV,
    _build_server,
    _dry_run_result,
)
from tractum.signing import (
    CONSENSUS_PAYLOAD_V2,
    ConsensusReceipt,
    Ed25519Backend,
    verify_receipt_detailed,
)

SPECIALISTS = [
    {"name": "ShipIt", "role": "Product Lead", "instructions": "ship it"},
    {"name": "Reliability", "role": "SRE", "instructions": "flag it"},
    {"name": "Security", "role": "Security Engineer", "instructions": "threat-model it"},
]


def _server():
    try:
        return _build_server()
    except ImportError:
        pytest.skip("mcp extra not installed")


async def _call(server, name: str, args: dict) -> dict:
    content, structured = await server.call_tool(name, args)
    if not isinstance(structured, dict):
        # Older mcp versions return raw content blocks instead of (blocks, dict).
        structured = json.loads(content[0].text)
    return structured


# --- dry-run stub consensus (no mcp needed) ----------------------------------


def test_dry_run_result_is_a_verifiable_v2_receipt():
    backend = Ed25519Backend()
    result = _dry_run_result(
        [AgentConfig(n, r, "") for n, r in
         (("A", "role a"), ("B", "role b"))],
        DRY_RUN_SWARM_NAME, "t1",
    )
    receipt = ConsensusReceipt.from_result(
        result, swarm_name=DRY_RUN_SWARM_NAME, task_id="t1"
    )
    assert receipt.payload["type"] == CONSENSUS_PAYLOAD_V2
    priv, pub = backend.generate_keypair()
    backend.sign_receipt(receipt, priv)
    report = verify_receipt_detailed(receipt, expected_operator_pubkey=pub)
    assert report.valid is True
    assert report.valid_statements == 2
    # Self-identifying: a dry-run receipt can't pass as a live decision.
    assert "[dry-run stub]" in result.final_answer
    assert all("[dry-run stub]" in r.answer for r in result.responses)


# --- signing-key policy (through the real server) -----------------------------


@pytest.mark.asyncio
async def test_reach_consensus_signs_ephemerally_without_a_pinned_key(monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_PINNED_KEY_ENV, raising=False)
    monkeypatch.delenv(DRY_RUN_ENV, raising=False)
    wire = await _call(_server(), "reach_consensus", {
        "question": "ship or flag?", "specialists": SPECIALISTS, "dry_run": True,
    })
    assert wire["metadata"]["operator_key"] == "ephemeral"
    assert wire["metadata"]["dry_run"] == "true"
    assert wire["signature"] and wire["public_key"]
    verdict = await _call(_server(), "verify_consensus", {
        "receipt": wire, "expected_operator_pubkey": wire["public_key"],
    })
    assert verdict["valid"] is True
    assert verdict["valid_statements"] == len(SPECIALISTS)


@pytest.mark.asyncio
async def test_reach_consensus_uses_pinned_key_when_set(monkeypatch):
    backend = Ed25519Backend()
    priv, pub = backend.generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, priv)
    wire = await _call(_server(), "reach_consensus", {
        "question": "ship or flag?", "specialists": SPECIALISTS, "dry_run": True,
    })
    assert wire["metadata"]["operator_key"] == "pinned"
    assert wire["public_key"] == pub
    verdict = await _call(_server(), "verify_consensus", {
        "receipt": wire, "expected_operator_pubkey": pub,
    })
    assert verdict["valid"] is True


@pytest.mark.asyncio
async def test_require_pinned_key_fails_loudly_when_key_is_unset(monkeypatch):
    # FastMCP surfaces tool exceptions as ToolError to the client — that IS
    # the loud failure; the message carries the fix.
    from mcp.server.fastmcp.exceptions import ToolError

    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    monkeypatch.setenv(REQUIRE_PINNED_KEY_ENV, "1")
    with pytest.raises(ToolError, match=REQUIRE_PINNED_KEY_ENV):
        await _call(_server(), "reach_consensus", {
            "question": "ship or flag?", "specialists": SPECIALISTS,
            "dry_run": True,
        })


@pytest.mark.asyncio
async def test_require_pinned_key_allows_set_key(monkeypatch):
    backend = Ed25519Backend()
    priv, pub = backend.generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, priv)
    monkeypatch.setenv(REQUIRE_PINNED_KEY_ENV, "1")
    wire = await _call(_server(), "reach_consensus", {
        "question": "ship or flag?", "specialists": SPECIALISTS, "dry_run": True,
    })
    assert wire["public_key"] == pub


@pytest.mark.asyncio
async def test_dry_run_env_flag_gates_the_stub_swarm(monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_PINNED_KEY_ENV, raising=False)
    monkeypatch.setenv(DRY_RUN_ENV, "1")
    wire = await _call(_server(), "reach_consensus", {
        "question": "ship or flag?", "specialists": SPECIALISTS,
    })
    assert wire["payload"]["swarm"] == DRY_RUN_SWARM_NAME
    assert wire["metadata"]["dry_run"] == "true"


# --- per-agent pubkey pinning on verify_consensus -----------------------------


@pytest.mark.asyncio
async def test_verify_consensus_pins_per_agent_pubkeys(monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_PINNED_KEY_ENV, raising=False)
    wire = await _call(_server(), "reach_consensus", {
        "question": "ship or flag?", "specialists": SPECIALISTS, "dry_run": True,
    })
    real_keys = {
        s["agent"]: s["public_key"] for s in wire["payload"]["statements"]
    }
    # Right keys: everything holds.
    verdict = await _call(_server(), "verify_consensus", {
        "receipt": wire, "expected_agent_pubkeys": real_keys,
    })
    assert verdict["valid"] is True
    # One wrong (rotated/replaced) agent key: that statement fails BY NAME.
    wrong = dict(real_keys)
    wrong["ShipIt"] = Ed25519Backend().generate_keypair()[1]
    verdict = await _call(_server(), "verify_consensus", {
        "receipt": wire, "expected_agent_pubkeys": wrong,
    })
    assert verdict["valid"] is False
    by_agent = {s["agent"]: s for s in verdict["statements"]}
    assert by_agent["ShipIt"]["reason"] == "key-mismatch"
    assert by_agent["Reliability"]["valid"] is True
