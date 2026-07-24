"""
Claudeway MCP server — expose consensus as a tool to any MCP client.

This is the distribution play. Run this server and any MCP-capable agent
(Claude Code, Goose, Buzz rooms, Cursor) gains a `reach_consensus` tool:
hand it a question + N specialist perspectives, get back a signed,
verifiable agreement. No framework to learn, no graphs to wire.

Run:
    pip install claudeway[mcp]
    claudeway-mcp            # stdio transport (Claude Code, Cursor)
    claudeway-mcp --http     # HTTP/SSE transport (remote agents)

The server is transport-agnostic; FastMCP picks the transport from how it's
invoked. Tools are async and reuse the claudeway core directly.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

from .agent import AgentConfig
from .consensus import ConsensusStrategy, Debate, WeightedVote
from .signing import ConsensusReceipt, Ed25519Backend
from .swarm import Swarm, SwarmConfig, Task
from .transports import to_json_receipt


def _build_server() -> Any:
    """Construct the FastMCP server. Imported lazily so [mcp] extra stays optional."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="claudeway",
        instructions=(
            "Claudeway gives you verifiable multi-agent consensus. Use "
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

        Returns:
            A signed ConsensusReceipt (JSON form): final_answer, agreement
            score, per-agent responses, and a cryptographic signature anyone
            can verify with `verify_consensus`.
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

        swarm = Swarm(
            SwarmConfig(name="mcp-consensus", description=question, agents=agent_configs),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            consensus=consensus,
        )
        task = Task(
            id=f"mcp-{asyncio.get_event_loop().time()}",
            description=question,
            input_data=context or {},
        )
        completed = await swarm.process(task)

        # Sign the result so the caller can prove provenance.
        receipt = ConsensusReceipt.from_result(
            _result_from_dict(completed.result),
            swarm_name=swarm.config.name,
            task_id=task.id,
        )
        backend = Ed25519Backend()
        priv = os.getenv("CLAUDEWAY_SIGNING_KEY")
        if priv:
            backend.sign_receipt(receipt, priv)
        return to_json_receipt(receipt)

    @mcp.tool()
    async def verify_consensus(receipt: dict[str, Any]) -> dict[str, bool]:
        """
        Verify a signed consensus receipt's integrity and signature.

        Args:
            receipt: A receipt dict as returned by reach_consensus.

        Returns:
            {"valid": true} if the signature matches and the payload is
            untampered; {"valid": false} otherwise (wrong key, tampered
            payload, or missing signature).
        """
        rebuilt = ConsensusReceipt(
            payload=receipt.get("payload", {}),
            algorithm=receipt.get("algorithm", ""),
            public_key=receipt.get("public_key", ""),
            signature=receipt.get("signature", ""),
            payload_hash=receipt.get("payload_hash", ""),
            signed_at=receipt.get("signed_at", ""),
        )
        valid = Ed25519Backend().verify_receipt(rebuilt)
        return {"valid": valid}

    return mcp


def _result_from_dict(d: dict[str, Any]):
    """Reconstruct a ConsensusResult from its dict form (as produced by Task.result)."""
    from .consensus import ConsensusResult
    from .swarm import AgentResponse

    responses = [
        AgentResponse(
            agent_name=r.get("agent", ""),
            answer=r.get("answer", ""),
            confidence=r.get("confidence", 0.5),
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
    """Entry point for the `claudeway-mcp` console script."""
    parser = argparse.ArgumentParser(description="Claudeway MCP server")
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
