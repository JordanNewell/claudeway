"""
MCP headline demo - pip install to a verifiable decision, end to end.

The launch story in one script: a 3-agent swarm reaches a decision, the
consensus receipt is produced exactly the way the MCP server produces it
(`tractum-mcp`), then verified — aggregate signature, quorum k-of-n, and
every agent's individual statement — through the server's own
`verify_consensus` tool.

    # keyless (offline stub agents - works in CI, no API key needed)
    python examples/mcp_demo.py

    # or with real Claude agents
    ANTHROPIC_API_KEY=sk-ant-... python examples/mcp_demo.py

Verification goes through the real MCP surface: when the `mcp` package is
installed (`pip install tractum[mcp]`), the demo calls the server's
registered `verify_consensus` tool directly; otherwise it falls back to the
same `verify_receipt_detailed` call the tool makes.

Requires: pip install tractum  (the [mcp] extra upgrades step 4 to the
real MCP tool call)
"""

import asyncio
import os
import sys
from datetime import UTC, datetime
from typing import Any

# Real-agent answers can carry Unicode; default Windows consoles are cp1252.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from tractum import (
    AgentConfig,
    AgentResponse,
    ConsensusReceipt,
    ConsensusResult,
    Ed25519Backend,
    Swarm,
    SwarmConfig,
    Task,
    WeightedVote,
)
from tractum.signing import AGENT_STATEMENT_TYPE
from tractum.transports import to_json_receipt

SWARM_NAME = "McpLaunchDemo"
TASK_ID = "launch-1"

QUESTION = (
    "Should we ship the new MCP server behind a feature flag or GA it in the "
    "next release?"
)


def mock_consensus() -> ConsensusResult:
    """Offline-mode consensus: three specialists vote, no API calls.

    Mirrors what Swarm.process does with real agents — including the v0.4.0
    per-agent statement signing — so the receipt downstream is the same v2,
    quorum-carrying artifact a live swarm produces.
    """
    stances = [
        ("ShipIt", "Product Lead", "ga", 0.82,
         "Distribution wins; the tool surface is small and revertible."),
        ("Reliability", "SRE / Platform Lead", "feature_flag", 0.61,
         "Unproven load path; flag it and watch p99s for a week."),
        ("Security", "Security Engineer", "ga", 0.77,
         "The tool is read-compute only; blast radius is a signed receipt."),
    ]
    backend = Ed25519Backend()
    responses = []
    for name, role, answer, confidence, reasoning in stances:
        # Each agent gets its own keypair and signs its own stance —
        # exactly what Swarm._provision_agent_keys + _sign_statement do.
        priv, _ = backend.generate_keypair()
        statement = {
            "type": AGENT_STATEMENT_TYPE,
            "swarm": SWARM_NAME,
            "task_id": TASK_ID,
            "agent": name,
            "role": role,
            "model": "mock",
            "round": 1,
            "answer": answer,
            "confidence": confidence,
            "signed_at": datetime.now(UTC).isoformat(),
        }
        responses.append(AgentResponse(
            agent_name=name, answer=answer, confidence=confidence,
            reasoning=reasoning, statement=backend.sign_statement(statement, priv),
        ))
    # 2 of 3 say ga with the higher confidence -> weighted vote lands there.
    return ConsensusResult(
        final_answer="ga",
        method="weighted_vote",
        agent_count=3,
        responses=responses,
        agreement=0.77,
        rounds=1,
    )


async def real_consensus() -> ConsensusResult:
    """Online mode: real Claude specialists debate via Tractum's Swarm."""
    swarm = Swarm(
        SwarmConfig(
            name=SWARM_NAME,
            description=QUESTION,
            agents=[
                AgentConfig("ShipIt", "Product Lead",
                            "You bias toward shipping and distribution."),
                AgentConfig("Reliability", "SRE / Platform Lead",
                            "You bias toward rollout safety and blast radius."),
                AgentConfig("Security", "Security Engineer",
                            "You bias toward attack surface and abuse paths."),
            ],
        ),
        api_key=os.environ["ANTHROPIC_API_KEY"],
        consensus=WeightedVote(),
    )
    completed = await swarm.process(Task(id=TASK_ID, description=QUESTION, input_data={}))
    r = completed.result
    return ConsensusResult(
        final_answer=r["final_answer"],
        method=r["method"],
        agent_count=r["agent_count"],
        responses=[
            AgentResponse(agent_name=resp["agent"], answer=resp["answer"],
                          confidence=resp["confidence"],
                          statement=resp.get("statement"))
            for resp in r["responses"]
        ],
        agreement=r["agreement"],
        rounds=r["rounds"],
        disagreed=r["disagreed"],
    )


def header(s: str) -> None:
    print(f"\n{'=' * 70}\n{s}\n{'=' * 70}")


async def main() -> None:
    use_real = bool(os.environ.get("ANTHROPIC_API_KEY"))
    header("Tractum MCP demo - decision to verifiable receipt"
           f"\n({'real Claude agents' if use_real else 'offline stub agents'})")
    print(f"question: {QUESTION}")

    # 1. Three agents reach consensus.
    header("Step 1 - three agents reach consensus")
    result = await real_consensus() if use_real else mock_consensus()
    print(f"final: {result.final_answer}")
    print(f"agreement: {result.agreement:.0%}")
    for r in result.responses:
        print(f"  - {r.agent_name} (conf {r.confidence:.2f}): {r.answer}")

    # 2. Produce the receipt the way the MCP server's reach_consensus does:
    #    from_result -> operator signature -> plain-JSON receipt on the wire.
    header("Step 2 - sign the receipt (same path as tractum-mcp)")
    receipt = ConsensusReceipt.from_result(
        result, swarm_name=SWARM_NAME, task_id=TASK_ID
    )
    backend = Ed25519Backend()
    operator_priv, operator_pub = backend.generate_keypair()
    backend.sign_receipt(receipt, operator_priv)
    wire = to_json_receipt(receipt)
    print(f"payload:    v{wire['payload']['type'].rsplit('v', 1)[-1]} "
          f"({len(wire['payload'].get('statements', []))} signed statements)")
    print(f"payload hash: {wire['payload_hash']}")
    print(f"quorum:     k-of-n = {wire['payload']['quorum']}-of-"
          f"{len(wire['payload']['statements'])}")
    print(f"algorithm:  {wire['algorithm']}")
    print(f"operator pubkey: {wire['public_key'][:24]}...")
    print(f"signature:  {wire['signature'][:32]}...")

    # 3. Verify — through the real MCP server's verify_consensus tool when
    #    the [mcp] extra is installed, else the same call it makes.
    header("Step 3 - verify (MCP verify_consensus)")
    verdict = await _verify_via_mcp_or_direct(wire, operator_pub)

    print(f"valid:            {verdict['valid']}")
    print(f"aggregate sig:    {verdict['aggregate_valid']} (pinned to operator key)")
    print(f"quorum met:       {verdict['valid_statements']}/{verdict['quorum']} "
          f"of {verdict['total_statements']} statements")
    for s in verdict["statements"]:
        print(f"  - {s['agent']}: {'valid' if s['valid'] else 'INVALID'}")

    header("Done")
    print("Same question over MCP: any MCP client gets this exact round trip")
    print("from `reach_consensus` + `verify_consensus`. No framework to learn.")


async def _verify_via_mcp_or_direct(
    wire: dict[str, Any], operator_pub: str
) -> dict[str, Any]:
    """Run the server's verify_consensus tool, or its direct equivalent.

    With `mcp` installed this drives the real FastMCP tool (the exact one
    `tractum-mcp` exposes), including operator-key pinning. Without it,
    the same verify_receipt_detailed call runs inline.
    """
    # _build_server imports mcp lazily, so the try must cover the call.
    try:
        from tractum.server import _build_server
        server = _build_server()
    except ImportError:
        server = None
    if server is None:
        from tractum import verify_receipt_detailed

        report = verify_receipt_detailed(
            ConsensusReceipt(
                payload=wire["payload"], algorithm=wire["algorithm"],
                public_key=wire["public_key"], signature=wire["signature"],
                payload_hash=wire["payload_hash"], signed_at=wire["signed_at"],
            ),
            expected_operator_pubkey=operator_pub,
        )
        print("(mcp not installed - verified via verify_receipt_detailed)")
        return {
            "valid": report.valid,
            "aggregate_valid": report.aggregate_valid,
            "quorum": report.quorum,
            "valid_statements": report.valid_statements,
            "total_statements": report.total_statements,
            "statements": [
                {"agent": s.agent, "valid": s.valid, "reason": s.reason}
                for s in report.statements
            ],
        }

    content, structured = await server.call_tool("verify_consensus", {
        "receipt": wire,
        "expected_operator_pubkey": operator_pub,
    })
    print("(verified through the tractum MCP server's verify_consensus tool)")
    if not isinstance(structured, dict):
        # Older mcp versions return raw content blocks instead of (blocks, dict).
        import json

        structured = json.loads(content[0].text)
    return structured


if __name__ == "__main__":
    asyncio.run(main())
