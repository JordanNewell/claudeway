---
title: Coordinator
description: Hierarchical task decomposition. One manager agent decomposes a task into sub-tasks, routes to specialists, runs in dependency order, synthesizes a final answer.
---

# Coordinator

`Coordinator` is hierarchical orchestration: one manager agent decomposes a task into sub-tasks, routes each to the right specialist, runs them in dependency order (parallel where independent), and synthesizes a final answer from the parts.

**Reach for `Swarm`** when you want multiple perspectives on the same question (adversarial check, confidence boost, signed receipt).
**Reach for `Coordinator`** when the work itself has parts (research → analyze → write, or any pipeline that benefits from role specialization).

---

## The flow

When you call `await coordinator.coordinate(task)`:

1. **Decompose** — the coordinator agent produces a JSON plan: `{"sub_tasks":[{"id","description","specialist","dependencies"}]}`. The plan is parsed for real (not hardcoded) — unparseable plans degrade silently to a single whole-task sub-task.
2. **Assign** — each sub-task is matched to a specialist via `_pick_specialist`: exact id → role-substring → first available → `None` (coordinator runs it).
3. **Execute** — sub-tasks whose dependencies are satisfied run together via `asyncio.gather`; dependent ones wait. Prior results are injected into each agent's prompt as context. Unknown or unresolvable dependencies fail the sub-task (never hang).
4. **Synthesize** — the coordinator agent folds all sub-results into a single final answer.

---

## Example

```python
import asyncio
import os
from claudeway import Agent, AgentConfig, Coordinator, CoordinatorConfig, Task

async def main():
    api_key = os.environ["ANTHROPIC_API_KEY"]
    coord = Coordinator(CoordinatorConfig(), api_key=api_key)

    def specialist(name, role, instructions):
        coord.add_sub_agent(name, Agent(AgentConfig(name, role, instructions), api_key=api_key))

    specialist("Researcher", "Research Specialist", "Gather and summarize relevant facts. Be concise.")
    specialist("Analyst",    "Risk Analyst",        "Evaluate options against criteria; surface tradeoffs.")
    specialist("Writer",     "Technical Writer",    "Turn analysis into a clear recommendation document.")

    task = Task(
        id="eval-1",
        description="Evaluate adopting TypeScript strict mode across our monorepo. Recommend.",
        input_data={"team_size": 8, "codebase_age_years": 3},
    )
    done = await coord.coordinate(task)

    r = done.result
    print("Plan:")
    for st in r["sub_tasks"]:
        print(f"  [{st['id']}] {st['assigned_to']}: {st['description'][:60]}")
    print("\nFinal:\n", r["final_answer"])

asyncio.run(main())
```

A typical plan from this setup:

```
[1] Researcher: survey strict-mode tradeoffs        (parallel)
[2] Analyst:    evaluate against team/codebase       (parallel)
[3] Writer:     draft recommendation                 (serial, depends on 1 + 2)
```

The Writer receives both prior results as context, so the synthesis is grounded.

---

## Return shape

`coordinate(task)` returns the same `Task` with `.result` populated as:

```python
{
    "final_answer":     str,
    "sub_task_count":   int,
    "sub_tasks":        [{"id", "description", "assigned_to", "status"}],
    "synthesis_method": "coordinator",
}
```

---

## API surface

```python
class Coordinator:
    def __init__(self, config: CoordinatorConfig, api_key: str | None = None)
    def add_sub_agent(self, agent_id: str, agent: Agent) -> None       # register a specialist
    def add_sub_swarm(self, swarm_id: str, swarm: Swarm) -> None       # see "Limits" below
    async def coordinate(self, task: Task) -> Task                     # returns same Task with .result set
```

`CoordinatorConfig` is a subclass of `AgentConfig` with built-in defaults (name, role, decomposition prompt, model, temperature, max_tokens). Override any by passing kwargs. See [Configuration](configuration.md#coordinatorconfig) for the field reference.

---

## Coordinator vs Swarm

| | **Coordinator** | **Swarm** |
|---|---|---|
| Topology | Hierarchical (1 manager → N specialists) | Peer-to-peer (N agents, one question) |
| Goal | Divide-and-conquer a multi-part task | Multiple perspectives, then agree |
| Execution | Dependency-respecting, partial parallelism | All agents run in parallel |
| Output | Synthesized answer from parts | Consensus result (+ optional Debate revision round) |
| Signed receipt | **No** | **Yes** (`ConsensusReceipt`, Ed25519 / ML-DSA) |
| Streaming events | **No** (`on_event` not wired) | **Yes** (`AgentCompleted`, `ConsensusResolved`) |
| Use when | Pipeline / role specialization | Adversarial check, confidence boost, verifiable receipt |

The verifiability moat — signed receipts, transparency log, `OnEvent` streaming — lives on `Swarm`, not here. Coordinator is the non-consensus execution path. If your downstream needs a signed artifact, wrap the Coordinator output yourself or use a Swarm at the synthesis step.

---

## Known limits (v0.3.x)

Honest about what's not finished:

- **No receipts, no events.** `coordinate()` returns a plain dict. If you need a signed artifact or streaming observability, you have to wrap it yourself (or use `Swarm`).
- **`add_sub_swarm` is a stub.** Sub-swarms are stored in `self.sub_swarms` but the dispatcher only routes to `self.sub_agents`. A sub-task the planner routes to a swarm won't actually reach it in v0.3.2.
- **Specialist routing falls back silently.** A `specialist_role` that doesn't exact-match an id or substring-match a role lands on the **first** registered specialist with no warning. A typo in the plan can send Analyst work to the Researcher.
- **Coordinator runs unmatched sub-tasks itself** via its own `self.agent` — useful, but means the "manager" burns tokens on execution if routing misses.
- **Plan degradation is invisible.** An unparseable or empty plan silently degrades to a single whole-task sub-task. The status string `"coordinator plan unparseable"` is the only signal — no warning is logged.
- **Hardcoded planner model.** `CoordinatorConfig` defaults to `claude-3-5-sonnet-20241022`. Override if you want Opus for harder planning or Haiku for cheaper.

---

## Live demo

[`examples/coordinator_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/coordinator_demo.py) runs the flow end-to-end with real Claude agents. The plan is parsed for real, specialists run in dependency order, results are synthesized.
