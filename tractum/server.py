"""
Tractum MCP server — expose consensus as a tool to any MCP client.

This is the distribution play. Run this server and any MCP-capable agent
(Claude Code, Cursor, Goose) gains a `reach_consensus` tool:
hand it a question + N specialist perspectives, get back a signed,
verifiable agreement. No framework to learn, no graphs to wire.

Run:
    pip install tractum[mcp]
    tractum-mcp            # stdio transport (Claude Code, Cursor)
    tractum-mcp --http     # HTTP/SSE transport (remote agents)

The server is transport-agnostic; FastMCP picks the transport from how it's
invoked. Tools are async and reuse the tractum core directly.

Signing keys:
    - TRACTUM_SIGNING_KEY (hex Ed25519 private key): when set, every receipt
      is signed by that stable operator key — pin it once, trust forever.
    - When unset, the server generates an EPHEMERAL keypair per receipt. The
      receipt is still signed and internally verifiable, but the key lives
      and dies with the response — verifiers must take the operator pubkey
      from the response itself (the wire `public_key` field; metadata
      `operator_key: ephemeral` marks the mode).
    - TRACTUM_REQUIRE_PINNED_KEY=1: deployments that must never ship an
      ephemeral-signed receipt set this to fail loudly instead.

Dry-run mode:
    TRACTUM_MCP_DRY_RUN=1 (or the per-call `dry_run` argument) replaces the
    live Claude swarm with deterministic offline stub agents — real keys,
    real signatures, no intelligence, no API calls. The receipt
    self-identifies (swarm name + stub answers + metadata) so a dry-run
    receipt can never pass as a live one.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from .agent import AgentConfig
from .consensus import ConsensusResult, ConsensusStrategy, Debate, WeightedVote
from .signing import (
    AGENT_STATEMENT_TYPE,
    ConsensusReceipt,
    Ed25519Backend,
    verify_receipt_detailed,
)
from .swarm import AgentResponse, Swarm, SwarmConfig, Task
from .transports import to_json_receipt

SIGNING_KEY_ENV = "TRACTUM_SIGNING_KEY"
REQUIRE_PINNED_KEY_ENV = "TRACTUM_REQUIRE_PINNED_KEY"
DRY_RUN_ENV = "TRACTUM_MCP_DRY_RUN"

DRY_RUN_SWARM_NAME = "mcp-consensus-dry-run"


def _env_flag(name: str) -> bool:
    """True when an env var is set to an affirmative value."""
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _build_server() -> Any:
    """Construct the FastMCP server. Imported lazily so [mcp] extra stays optional."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="tractum",
        instructions=(
            "Tractum gives you verifiable multi-agent consensus. Use "
            "`reach_consensus` when a question deserves multiple specialist "
            "perspectives that must agree (not just one answer). Use "
            "`verify_consensus` to check a previously-issued receipt."
        ),
    )

    @mcp.tool()
    async def reach_consensus(
        question: str,
        specialists: list[dict[str, str]],
        strategy: str = "weighted_vote",
        context: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Run a swarm of specialist agents and return a signed consensus receipt.

        Args:
            question: The question requiring agreement.
            specialists: List of {name, role, instructions} for each agent.
                At least 2 recommended; 3-5 typical.
            strategy: "weighted_vote" (cheap, default) or "debate" (one
                revision round when agents disagree — more calls, higher
                quality on hard questions).
            context: Optional dict of input data to feed the swarm.
            dry_run: Run deterministic offline stub agents instead of live
                Claude calls (no ANTHROPIC_API_KEY needed). Also enabled by
                the TRACTUM_MCP_DRY_RUN=1 env var. The receipt self-identifies
                as a dry run — never treat one as a real decision.

        Returns:
            A signed ConsensusReceipt (JSON form): final_answer, agreement
            score, per-agent responses, and a cryptographic signature anyone
            can verify with `verify_consensus`. Signed with
            TRACTUM_SIGNING_KEY when set; otherwise an ephemeral keypair
            whose public key is in the response (`public_key`, and metadata
            `operator_key: ephemeral`).
        """
        if not specialists:
            return {"error": "at least one specialist is required"}

        agent_configs = [
            AgentConfig(
                name=s["name"],
                role=s["role"],
                instructions=s.get("instructions", ""),
                model=s.get("model", "claude-3-5-sonnet-20241022"),
            )
            for s in specialists
        ]
        consensus: ConsensusStrategy
        if strategy == "debate":
            consensus = Debate()
        else:
            consensus = WeightedVote()

        dry_run = dry_run or _env_flag(DRY_RUN_ENV)
        task_id = f"mcp-{asyncio.get_event_loop().time()}"
        swarm_name = DRY_RUN_SWARM_NAME if dry_run else "mcp-consensus"

        if dry_run:
            result = _dry_run_result(agent_configs, swarm_name, task_id)
        else:
            swarm = Swarm(
                SwarmConfig(name=swarm_name, description=question, agents=agent_configs),
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                consensus=consensus,
            )
            task = Task(id=task_id, description=question, input_data=context or {})
            completed = await swarm.process(task)
            result = _result_from_dict(completed.result)

        # Sign the result so the caller can prove provenance.
        receipt = ConsensusReceipt.from_result(
            result, swarm_name=swarm_name, task_id=task_id
        )
        backend = Ed25519Backend()
        if _env_flag(REQUIRE_PINNED_KEY_ENV) and not os.getenv(SIGNING_KEY_ENV):
            raise ValueError(
                f"{REQUIRE_PINNED_KEY_ENV} is set but {SIGNING_KEY_ENV} is not. "
                f"Set {SIGNING_KEY_ENV} to a hex Ed25519 private key, or unset "
                f"{REQUIRE_PINNED_KEY_ENV} to allow ephemeral per-receipt keys."
            )
        pinned = os.getenv(SIGNING_KEY_ENV, "")
        if pinned:
            backend.sign_receipt(receipt, pinned)
            receipt.metadata["operator_key"] = "pinned"
        else:
            # No operator key configured: sign with a fresh ephemeral pair so
            # the receipt is still internally verifiable. The public key is in
            # the response; a verifier who needs more than single-receipt
            # integrity should pin a stable TRACTUM_SIGNING_KEY instead.
            ephem_priv, _ = backend.generate_keypair()
            backend.sign_receipt(receipt, ephem_priv)
            receipt.metadata["operator_key"] = "ephemeral"
        if dry_run:
            receipt.metadata["dry_run"] = "true"
        return to_json_receipt(receipt)

    @mcp.tool()
    async def verify_consensus(
        receipt: dict[str, Any],
        expected_operator_pubkey: str = "",
        expected_agent_pubkeys: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Verify a signed consensus receipt: integrity, signature, agent
        statements, and quorum.

        Args:
            receipt: A receipt dict as returned by reach_consensus.
            expected_operator_pubkey: Optional hex key the receipt MUST be
                signed by. Without pinning, anyone can re-sign a doctored
                payload with their own key — pinning is what makes the
                verdict mean something.
            expected_agent_pubkeys: Optional map of agent name -> hex public
                key that each agent's statement MUST be signed by. Without
                it, a signature only proves self-consistency, not that the
                agent you know cast that stance.

        Returns:
            {"valid": true} iff the payload is untampered, the aggregate
            signature verifies (under the pinned key, if given), and enough
            valid per-agent statements meet the quorum. "statements" details
            each agent's check; "quorum"/"valid_statements" report the count.
        """
        rebuilt = ConsensusReceipt(
            payload=receipt.get("payload", {}),
            algorithm=receipt.get("algorithm", ""),
            public_key=receipt.get("public_key", ""),
            signature=receipt.get("signature", ""),
            payload_hash=receipt.get("payload_hash", ""),
            signed_at=receipt.get("signed_at", ""),
        )
        report = verify_receipt_detailed(
            rebuilt,
            expected_operator_pubkey=expected_operator_pubkey,
            expected_agent_pubkeys=expected_agent_pubkeys,
        )
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

    return mcp


def _dry_run_result(
    agent_configs: list[AgentConfig], swarm_name: str, task_id: str
) -> ConsensusResult:
    """
    Deterministic offline consensus for dry-run mode (same approach as
    examples/mcp_demo.py: per-agent ephemeral keypairs, real statement
    signatures, stub stances). Everything about the output is marked
    dry-run — swarm name, answers, model — so the resulting receipt can't
    be mistaken for (or quietly swapped into the place of) a live decision.
    """
    backend = Ed25519Backend()
    responses: list[AgentResponse] = []
    for i, cfg in enumerate(agent_configs):
        answer = (
            f"[dry-run stub] {cfg.name} ({cfg.role}) would argue their "
            "specialist position here."
        )
        priv, _ = backend.generate_keypair()
        statement = {
            "type": AGENT_STATEMENT_TYPE,
            "swarm": swarm_name,
            "task_id": task_id,
            "agent": cfg.name,
            "role": cfg.role,
            "model": "dry-run-stub",
            "round": 1,
            "answer": answer,
            "confidence": 0.9 - 0.05 * i,
            "signed_at": datetime.now(UTC).isoformat(),
        }
        responses.append(AgentResponse(
            agent_name=cfg.name,
            answer=answer,
            confidence=statement["confidence"],
            reasoning="dry-run stub response — no live agents were called",
            statement=backend.sign_statement(statement, priv),
        ))
    return ConsensusResult(
        final_answer="[dry-run stub] no live consensus was computed",
        method="weighted_vote",
        agent_count=len(responses),
        responses=responses,
        agreement=0.0,
        rounds=1,
    )


def _result_from_dict(d: dict[str, Any]) -> ConsensusResult:
    """Reconstruct a ConsensusResult from its dict form (as produced by Task.result)."""
    responses = [
        AgentResponse(
            agent_name=r.get("agent", ""),
            answer=r.get("answer", ""),
            confidence=r.get("confidence", 0.5),
            statement=r.get("statement"),
        )
        for r in d.get("responses", [])
    ]
    return ConsensusResult(
        final_answer=d.get("final_answer", ""),
        method=d.get("method", ""),
        agent_count=d.get("agent_count", 0),
        responses=responses,
        agreement=d.get("agreement", 0.0),
        rounds=d.get("rounds", 1),
        disagreed=d.get("disagreed", False),
    )


def main() -> None:
    """Entry point for the `tractum-mcp` console script."""
    parser = argparse.ArgumentParser(description="Tractum MCP server")
    parser.add_argument(
        "--http", action="store_true",
        help="Serve over HTTP/SSE instead of stdio (for remote agents).",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="HTTP host (default 127.0.0.1)."
    )
    parser.add_argument(
        "--port", type=int, default=8765, help="HTTP port (default 8765)."
    )
    args = parser.parse_args()

    server = _build_server()
    if args.http:
        server.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        server.run()


if __name__ == "__main__":
    main()
