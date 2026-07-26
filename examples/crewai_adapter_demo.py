"""
CrewAI adapter demo — Claudeway consensus inside a CrewAI crew.

Two flows, mirroring the LangGraph adapter demo:

  1. Tool shape: a CrewAI Agent with `reach_consensus(swarm)` in its tool
     belt. The agent decides when to call consensus. The wedge case —
     CrewAI does the orchestration, Claudeway does the agreement.

  2. Flow shape: a prebuilt ConsensusFlow. question in -> signed agreement
     out. Idiomatic for users who orchestrate with Flows.

Requires ANTHROPIC_API_KEY. Uses Haiku + small max_tokens to keep it cheap.

    pip install -e ".[crewai]"
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/crewai_adapter_demo.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from claudeway import AgentConfig, Swarm, SwarmConfig  # noqa: E402
from claudeway.adapters.crewai import (  # noqa: E402
    ConsensusFlow,
    reach_consensus,
)

QUESTION = "Should a solo dev pick Postgres, SQLite, or Supabase for a side project?"


def build_swarm() -> Swarm:
    return Swarm(
        SwarmConfig(
            name="CrewChoice",
            description=QUESTION,
            agents=[
                AgentConfig(
                    "Dba", "Senior DBA",
                    "You weigh reliability and ops cost.",
                    model="claude-3-5-haiku-20241022",
                    max_tokens=256,
                ),
                AgentConfig(
                    "Indie", "Indie Hacker",
                    "You optimize for setup time and zero maintenance.",
                    model="claude-3-5-haiku-20241022",
                    max_tokens=256,
                ),
                AgentConfig(
                    "Security", "Security Engineer",
                    "You care about data safety and access control.",
                    model="claude-3-5-haiku-20241022",
                    max_tokens=256,
                ),
            ],
        ),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


async def flow1_tool() -> None:
    """The wedge case: a CrewAI agent with the consensus tool."""
    from crewai import LLM, Agent, Crew, Task

    print(f"\n{'=' * 70}\nFlow 1 - CrewAI agent calls Claudeway consensus tool\n{'=' * 70}")

    llm = LLM(
        model="anthropic/claude-3-5-haiku-20241022",
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_tokens=128,
    )
    tool = reach_consensus(build_swarm(), sign=True)

    agent = Agent(
        role="Decider",
        goal="Reach consensus on the question via your reach_consensus tool.",
        backstory="You delegate hard questions to a multi-agent panel and report the agreement.",
        llm=llm,
        tools=[tool],
        allow_delegation=False,
        verbose=False,
    )
    task = Task(
        description=f"Use reach_consensus to decide: {QUESTION}",
        expected_output="The consensus answer with agreement score.",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], verbose=False)

    # CrewAI's kickoff is sync; run in executor.
    result = await asyncio.to_thread(crew.kickoff)
    print(f"crew result: {str(result)[:300]}")


async def flow2_prebuilt_flow() -> None:
    """Prebuilt ConsensusFlow: question in -> signed agreement out."""
    print(f"\n{'=' * 70}\nFlow 2 - prebuilt ConsensusFlow\n{'=' * 70}")

    flow = ConsensusFlow(build_swarm(), sign=True, task_id="demo-flow-1")
    await flow.kickoff_async(inputs={"question": QUESTION})

    state = flow.state
    print(f"final answer: {state.final_answer}")
    print(f"agreement: {state.agreement:.0%}   disagreed: {state.disagreed}")
    for r in state.responses:
        print(f"  - {r['agent']} (conf {r['confidence']:.2f}): {r['answer'][:80]}...")
    if state.receipt:
        print(f"signed receipt: algorithm={state.receipt['algorithm']} "
              f"sig={state.receipt['signature'][:24]}...")


async def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY to run this demo.")
        return
    await flow1_tool()
    await flow2_prebuilt_flow()


if __name__ == "__main__":
    asyncio.run(main())
