"""
LangGraph adapter demo — Claudeway consensus as a node in a LangGraph graph.

Two flows:

  1. Prebuilt subgraph standalone: question in -> signed agreement out.
     The zero-config path. Use this when consensus is the whole job.

  2. Consensus node inside a user's own StateGraph: upstream research node,
     then consensus. The wedge case — this is what "LangGraph makes you wire
     coordination by hand; Claudeway is the node that does it for you" looks
     like in practice.

Requires ANTHROPIC_API_KEY (real Claude agents). The adapter itself is
offline-testable; this demo exercises the live path.

    pip install langgraph
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/langgraph_adapter_demo.py
"""

import asyncio
import os
import sys

# Allow running from a checkout without `pip install`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from claudeway import AgentConfig, Swarm, SwarmConfig  # noqa: E402
from claudeway.adapters.langgraph import (  # noqa: E402
    build_consensus_graph,
    make_consensus_node,
)

QUESTION = (
    "We're choosing a database for a side project with modest traffic. "
    "Postgres, SQLite, or a managed offering like Supabase?"
)


def build_swarm() -> Swarm:
    return Swarm(
        SwarmConfig(
            name="DbChoice",
            description=QUESTION,
            agents=[
                AgentConfig(
                    "Dba", "Senior DBA",
                    "You weigh reliability, ops cost, and operational maturity.",
                ),
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


async def flow1_prebuilt() -> None:
    print(f"\n{'=' * 70}\nFlow 1 - prebuilt consensus subgraph\n{'=' * 70}")
    graph = build_consensus_graph(build_swarm(), sign=True, task_id="flow-1")
    result = await graph.ainvoke({"question": QUESTION})

    print(f"final answer: {result['final_answer']}")
    print(f"agreement: {result['agreement']:.0%}   disagreed: {result['disagreed']}")
    for r in result["responses"]:
        print(f"  - {r['agent']} (conf {r['confidence']:.2f}): {r['answer'][:80]}...")
    print(f"signed receipt: algorithm={result['receipt']['algorithm']} "
          f"sig={result['receipt']['signature'][:24]}...")


async def flow2_embedded() -> None:
    """The wedge case: consensus as one node in a user's own graph."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    print(f"\n{'=' * 70}\nFlow 2 - consensus node inside a user StateGraph\n{'=' * 70}")

    class MyState(TypedDict, total=False):
        question: str
        research: str
        final_answer: str
        agreement: float
        disagreed: bool

    async def research_node(state):
        # Upstream work: contextualize the question before consensus.
        return {"research": f"prior art on: {state['question']}"}

    consensus = make_consensus_node(build_swarm())

    builder = StateGraph(MyState)
    builder.add_node("research", research_node)
    builder.add_node("consensus", consensus)
    builder.add_edge(START, "research")
    builder.add_edge("research", "consensus")
    builder.add_edge("consensus", END)

    app = builder.compile()
    result = await app.ainvoke({"question": QUESTION})

    print(f"research node produced: {result['research'][:80]}...")
    print(f"consensus final answer: {result['final_answer']}")
    print(f"agreement: {result['agreement']:.0%}   disagreed: {result['disagreed']}")


async def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY to run this demo.")
        return
    await flow1_prebuilt()
    await flow2_embedded()


if __name__ == "__main__":
    asyncio.run(main())
