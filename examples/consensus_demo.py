"""
Consensus demo - the killer example.

Three specialists disagree on a hard architectural question. Claudeway runs
WeightedVote, surfaces the disagreement explicitly, then re-runs Debate so
the agents see each other's reasoning and converge. The result is signed.

This is the thing you show next to a CrewAI/LangGraph answer to say:
"here, disagreement is surfaced and resolved, not averaged away."

    python examples/consensus_demo.py
"""

import asyncio
import os

from claudeway import (
    AgentConfig,
    ConsensusReceipt,
    ConsensusResult,
    Debate,
    Ed25519Backend,
    Swarm,
    SwarmConfig,
    Task,
    WeightedVote,
)
from claudeway.transports import to_json_receipt

QUESTION = (
    "We're choosing a multi-region backend architecture for a payments product "
    "with strong consistency needs. Active-active Postgres, or a CRDT datastore "
    "like FoundationDB, or message-passing with eventual consistency?"
)


def build_swarm(strategy) -> Swarm:
    return Swarm(
        SwarmConfig(
            name="ArchReview",
            description=QUESTION,
            agents=[
                AgentConfig(
                    "StrongConsistency",
                    "Distributed Systems Engineer",
                    "You prioritize strong consistency and correctness above all. "
                    "You are skeptical of eventual consistency for payments.",
                ),
                AgentConfig(
                    "Operations",
                    "SRE / Platform Lead",
                    "You prioritize operational simplicity and on-call burden. "
                    "Complex active-active setups worry you.",
                ),
                AgentConfig(
                    "Pragmatist",
                    "Staff Engineer",
                    "You balance correctness, cost, and time-to-market. "
                    "You favor boring technology that fits the team's skills.",
                ),
            ],
        ),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        consensus=strategy,
    )


def new_task() -> Task:
    return Task(id="arch-1", description=QUESTION, input_data={})


async def run_round(label: str, swarm: Swarm) -> dict:
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    # Each round needs a fresh task (the swarm appends to message history).
    completed = await swarm.process(new_task())
    r = completed.result
    print(f"final answer: {r['final_answer'][:200]}...")
    print(f"agreement: {r['agreement']:.0%}   disagreed: {r['disagreed']}")
    for resp in r["responses"]:
        print(f"  - {resp['agent']} (conf {resp['confidence']:.2f}): "
              f"{resp['answer'][:80]}...")
    return r


async def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY to run this demo.")
        return

    # Round 1: cheap. WeightedVote surfaces disagreement without extra calls.
    r1 = await run_round("Round 1 — WeightedVote (cheap)", build_swarm(WeightedVote()))

    if not r1["disagreed"]:
        print("\nAgents already agreed — skipping debate round.")
        return

    print("\nDisagreement flagged. Running Debate so agents see each other's reasoning...")

    # Round 2: Debate. Agents revise in light of peers. Costs more, converges harder.
    r2 = await run_round("Round 2 — Debate (revised)", build_swarm(Debate()))

    # Sign the final (debated) result.
    final = ConsensusResult(
        final_answer=r2["final_answer"],
        method=r2["method"],
        agent_count=r2["agent_count"],
        agreement=r2["agreement"],
        rounds=r2["rounds"],
        disagreed=r2["disagreed"],
    )
    receipt = ConsensusReceipt.from_result(final, swarm_name="ArchReview", task_id="arch-1")
    priv, pub = Ed25519Backend().generate_keypair()
    Ed25519Backend().sign_receipt(receipt, priv)

    print(f"\n{'=' * 70}\nSigned receipt\n{'=' * 70}")
    print(f"algorithm: {receipt.algorithm}")
    print(f"public key: {pub[:24]}...")
    print(f"signature: {receipt.signature[:24]}...")
    print(
        "verify with: to_json_receipt(...) + "
        "Ed25519Backend().verify_receipt(...)"
    )
    print(f"\nFull receipt: {to_json_receipt(receipt)}"[:400], "...")


if __name__ == "__main__":
    asyncio.run(main())
