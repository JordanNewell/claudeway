"""
Microsoft Agent Framework (MAF) adapter demo — Claudeway consensus as a
node in a MAF workflow.

Two flows:

  1. Prebuilt workflow standalone: question in -> signed agreement out.
     The zero-config path. Use this when consensus is the whole job.

  2. Consensus executor inside a user's own WorkflowBuilder: upstream
     research executor, then consensus. The wedge case — this is what
     "MAF gives you typed executors and a graph; Claudeway is the executor
     that does the agreement for you" looks like in practice.

Requires ANTHROPIC_API_KEY (real Claude agents). The adapter itself is
offline-testable; this demo exercises the live path.

    pip install claudeway[maf]
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/maf_adapter_demo.py
"""

import asyncio
import os
import sys

# Allow running from a checkout without `pip install`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from claudeway import AgentConfig, Swarm, SwarmConfig  # noqa: E402
from claudeway.adapters.maf import (  # noqa: E402
    build_consensus_workflow,
    make_consensus_executor,
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


def _first_output(run_result) -> dict:
    outputs = run_result.get_outputs()
    return outputs[0]


async def flow1_prebuilt() -> None:
    print(f"\n{'=' * 70}\nFlow 1 - prebuilt consensus workflow\n{'=' * 70}")
    workflow = build_consensus_workflow(build_swarm(), sign=True, task_id="flow-1")
    result = await workflow.run(QUESTION)
    payload = _first_output(result)

    print(f"final answer: {payload['final_answer']}")
    print(f"agreement: {payload['agreement']:.0%}   disagreed: {payload['disagreed']}")
    for r in payload["responses"]:
        print(f"  - {r['agent']} (conf {r['confidence']:.2f}): {r['answer'][:80]}...")
    receipt = payload["receipt"]
    print(f"signed receipt: algorithm={receipt['algorithm']} "
          f"sig={receipt['signature'][:24]}...")


async def flow2_embedded() -> None:
    """The wedge case: consensus as one executor in a user's own workflow."""
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

    print(f"\n{'=' * 70}\nFlow 2 - consensus executor inside a user WorkflowBuilder\n{'=' * 70}")

    class ResearchExecutor(Executor):
        """Upstream work: contextualize the question before consensus."""

        @handler
        async def research(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(f"prior art on: {message}")

    research = ResearchExecutor(id="research")
    consensus = make_consensus_executor(build_swarm())(id="claudeway_consensus")

    builder = WorkflowBuilder(start_executor=research, output_from=[consensus])
    builder.add_edge(research, consensus)
    workflow = builder.build()

    result = await workflow.run(QUESTION)
    payload = _first_output(result)

    print(f"consensus final answer: {payload['final_answer']}")
    print(f"agreement: {payload['agreement']:.0%}   disagreed: {payload['disagreed']}")


async def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY to run this demo.")
        return
    await flow1_prebuilt()
    await flow2_embedded()


if __name__ == "__main__":
    asyncio.run(main())
