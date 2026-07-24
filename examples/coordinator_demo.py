"""
Coordinator demo - real hierarchical decomposition.

A coordinator agent breaks a complex task into sub-tasks, assigns each to a
specialist, and runs them in dependency order (parallel where independent).
This is the pattern LangGraph makes you wire by hand; here it's one call.

Run:
    python examples/coordinator_demo.py
"""

import asyncio
import os

from claudeway import Agent, AgentConfig, Coordinator, CoordinatorConfig, Task


async def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY to run this demo.")
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")

    # The coordinator plans and delegates.
    coordinator = Coordinator(CoordinatorConfig(), api_key=api_key)

    # Specialists it can delegate to. The coordinator's decomposition plan
    # names which role should handle each sub-task; Claudeway routes to the
    # matching specialist and runs independent ones in parallel.
    coordinator.add_sub_agent(
        "Researcher",
        Agent(
            AgentConfig(
                "Researcher",
                "Research Specialist",
                "You gather and summarize relevant facts. Be concise.",
            ),
            api_key=api_key,
        ),
    )
    coordinator.add_sub_agent(
        "Analyst",
        Agent(
            AgentConfig(
                "Analyst",
                "Risk Analyst",
                "You evaluate options against criteria and surface tradeoffs.",
            ),
            api_key=api_key,
        ),
    )
    coordinator.add_sub_agent(
        "Writer",
        Agent(
            AgentConfig(
                "Writer",
                "Technical Writer",
                "You turn analysis into a clear recommendation document.",
            ),
            api_key=api_key,
        ),
    )

    task = Task(
        id="eval-1",
        description=(
            "Evaluate whether we should adopt TypeScript strict mode across "
            "our Python-and-TypeScript monorepo. Produce a recommendation."
        ),
        input_data={"team_size": 8, "codebase_age_years": 3},
    )

    print("Submitting task to coordinator...\n")
    completed = await coordinator.coordinate(task)
    r = completed.result

    print("=" * 70)
    print("COORDINATOR'S DECOMPOSITION (real, parsed from the plan):")
    print("=" * 70)
    for st in r["sub_tasks"]:
        dep_ids = st.get("dependencies") or []
        deps = " <- depends on " + ",".join(dep_ids) if dep_ids else ""
        line = f"  [{st['id']}] {st['assigned_to'] or 'coordinator'}: "
        print(f"{line}{st['description'][:70]}...{deps}")

    print("\n" + "=" * 70)
    print("FINAL SYNTHESIS:")
    print("=" * 70)
    print(r["final_answer"])


if __name__ == "__main__":
    asyncio.run(main())
