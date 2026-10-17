"""
Quickstart - the smallest useful Tractum program.

Run a 3-agent swarm, get a signed consensus answer. ~15 lines.

    pip install tractum
    export ANTHROPIC_API_KEY=...
    python examples/quickstart.py
"""

import asyncio
import os

from tractum import AgentConfig, ConsensusReceipt, Ed25519Backend, Swarm, SwarmConfig, Task


async def main() -> None:
    swarm = Swarm(
        SwarmConfig(
            name="Quickstart",
            description="Pick a database for a small side project",
            agents=[
                AgentConfig("Dba", "Senior DBA", "You weigh reliability and ops cost."),
                AgentConfig(
                    "Indie", "Indie Hacker",
                    "You optimize for setup time and zero maintenance.",
                ),
                AgentConfig(
                    "Security", "Security Engineer",
                    "You care about data safety and access control.",
                ),
            ],
        ),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    # Run consensus. WeightedVote by default — cheap, one round.
    task = Task(
        id="q1",
        description=(
            "Which database should a solo developer use for a side project "
            "with modest traffic?"
        ),
        input_data={},
    )
    completed = await swarm.process(task)

    # Sign the result so it's a verifiable attestation, not just text.
    receipt = ConsensusReceipt.from_result(
        _result(completed.result), swarm_name="Quickstart", task_id="q1"
    )
    Ed25519Backend().sign_receipt(receipt, _key())

    print("\n=== Consensus ===")
    print(completed.result["final_answer"])
    print(f"\nagreement: {completed.result['agreement']:.0%}  "
          f"disagreed: {completed.result['disagreed']}")
    print(f"\nsigned receipt (verify with tractum): "
          f"algorithm={receipt.algorithm} sig={receipt.signature[:24]}...")


def _result(d: dict):
    """Rebuild a ConsensusResult from its dict form for signing."""
    from tractum import AgentResponse, ConsensusResult
    return ConsensusResult(
        final_answer=d["final_answer"],
        method=d["method"],
        agent_count=d["agent_count"],
        responses=[
            AgentResponse(
                agent_name=r["agent"],
                answer=r["answer"],
                confidence=r["confidence"],
                statement=r.get("statement"),
            )
            for r in d.get("responses", [])
        ],
        agreement=d["agreement"],
        rounds=d["rounds"],
        disagreed=d["disagreed"],
    )


def _key() -> str:
    """A fresh signing key for the demo (persist TRACTUM_SIGNING_KEY in real use)."""
    key = os.getenv("TRACTUM_SIGNING_KEY")
    if key:
        return key
    priv, _ = Ed25519Backend().generate_keypair()
    return priv


if __name__ == "__main__":
    asyncio.run(main())
