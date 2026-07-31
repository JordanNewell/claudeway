---
title: Streaming events
description: Observe consensus as it happens. Wire an on_event callback into a Swarm and watch each agent land, the consensus resolve, and the receipt sign — in real time.
---

# Streaming events

A `Swarm.process(task)` call returns the final `ConsensusResult` — the answer. But the *process* — agents answering one by one, agreement tightening, rounds unfolding — is a black box by default.

**Streaming events open that box.** Wire an `on_event` callback into a `Swarm` (or flip `stream=True` in an adapter) and you observe consensus *as it happens*: per-agent answers and confidence the moment each lands, the resolved consensus at the end, and (when signing) the signed receipt as a final attestation.

This is **observable consensus** — a UI can render agents answering live, a transparency log can ingest each result, a debug harness can see where a run diverged.

---

## Event types

All events inherit `ConsensusEvent` (base fields: `schema_version="1.0"`, `swarm_id`, `task_id`, `kind`).

### `AgentCompleted`

Fires inside `asyncio.gather` the instant each agent's answer lands — before consensus is resolved. The headline streaming event.

```python
kind: "agent_completed"
agent: str          # agent name
answer: str         # the agent's answer
confidence: float   # agent self-reported confidence
round: int = 1      # consensus round (1 for single-round swarms)
```

### `ConsensusResolved`

Fires once per run, after the consensus strategy returns. Carries the headline numbers.

```python
kind: "consensus_resolved"
final_answer: str
method: str         # e.g. "weighted_vote"
agreement: float    # 0.0–1.0
rounds: int
disagreed: bool     # True if the swarm failed to agree
```

### `consensus_receipt` (MAF adapter only, when `sign=True`)

A signed attestation yielded as a final intermediate event so stream consumers receive the cryptographic receipt. Payload is the `ConsensusReceipt.to_dict()` merged with `kind="consensus_receipt"`: `algorithm`, `public_key`, `signature`, `payload_hash`, `signed_at`, plus the canonical `payload`. Not a `ConsensusEvent` subclass — it's the receipt dict with a `kind` discriminator added.

---

## The `OnEvent` callback

```python
OnEvent = Callable[[ConsensusEvent], Awaitable[None]]
```

Register by passing `on_event=` to `Swarm(...)`:

```python
swarm = Swarm(config, api_key=..., on_event=my_callback)
```

Or set `swarm.on_event` at runtime — adapters do this per-invoke and restore the prior value in a `finally` block.

**Threading model:** the callback runs **inline inside the swarm's event loop**, not on a separate thread. `AgentCompleted` fires from within each agent's gathered coroutine; `ConsensusResolved` fires once after `consensus.resolve(...)` returns. **Observer errors are swallowed** (logged to stdout) — a buggy observer can never change the consensus outcome or kill a run.

---

## Usage from a vanilla Swarm

Yes — streaming works directly on `Swarm`, no adapter required.

```python
from claudeway import Swarm, SwarmConfig, AgentConfig
from claudeway.events import AgentCompleted, ConsensusResolved

async def on_event(event):
    if isinstance(event, AgentCompleted):
        print(f"[{event.agent}] conf={event.confidence:.2f}: {event.answer[:60]}")
    elif isinstance(event, ConsensusResolved):
        print(f"CONSENSUS ({event.method}, agreement={event.agreement:.0%}): {event.final_answer}")

swarm = Swarm(config, api_key=..., on_event=on_event)
await swarm.process(task)
```

**Import note:** events are NOT yet re-exported from `claudeway/__init__.py` — import them from `claudeway.events`.

---

## Usage from the MAF adapter

`maf_adapter_demo.py` flow 3 — `build_consensus_workflow(swarm, stream=True, sign=True)` then consume via `workflow.run(prompt, stream=True)`:

```python
workflow = build_consensus_workflow(swarm, stream=True, sign=True, task_id="flow-3")

async for event in workflow.run(QUESTION, stream=True):
    if event.type != "intermediate":
        continue
    data = event.data
    if data.get("kind") == "agent_completed":
        print(f"  [{data['agent']}] conf={data['confidence']:.2f} round={data['round']}")
    elif data.get("kind") == "consensus_resolved":
        print(f"  CONSENSUS: agreement={data['agreement']:.0%}")
    elif data.get("kind") == "consensus_receipt":
        print(f"  SIGNED: {data['algorithm']} sig={data['signature'][:24]}...")
```

The adapter sets `swarm.on_event` to forward each event to `ctx.yield_output(event.model_dump())`, restores the prior callback in a `finally`, and (when signing) emits the receipt as one extra intermediate. MAF forbids an executor being in both `output_from` and `intermediate_output_from`, so streaming builds are **intermediate-only** — the final consensus is the `consensus_resolved` event, not a terminal output.

---

## Adapter support matrix

| Adapter | Streaming? | Mechanism |
|---|---|---|
| **Vanilla `Swarm`** | Yes | `on_event=` callback (inline, awaited) |
| **MAF** | Yes | `stream=True` → `intermediate_output_from`, consumed via `workflow.run(prompt, stream=True)` |
| **LangGraph** | Yes | `stream=True` → `get_stream_writer()`, consumed via `graph.astream(..., stream_mode="custom")` |
| **CrewAI** | No | Adapter has no `stream` parameter; consensus is a black box until the step returns |
| **Custom adapter** | Trivial | Set `swarm.on_event = your_async_callback` per-invoke, restore in `finally` (copy the MAF pattern) |

---

## Composability with the transparency log

Events and the transparency log compose naturally. `AgentCompleted`/`ConsensusResolved` are observation-only; the **receipt** is what enters the log.

The pattern (from `transparency_demo.py`): capture the `consensus_receipt` event in your stream consumer, hydrate it via `ConsensusReceipt(**data)` (or build from `ConsensusResult` via `ConsensusReceipt.from_result`), then `log.append(receipt)` to add it as a Merkle leaf. Later, anyone can verify inclusion with just the receipt + an inclusion proof + the published log root — no Claudeway trust required.

```python
# Inside your stream consumer:
elif data.get("kind") == "consensus_receipt":
    receipt = ConsensusReceipt(
        payload=data["payload"],
        algorithm=data["algorithm"],
        public_key=data["public_key"],
        signature=data["signature"],
        payload_hash=data["payload_hash"],
        signed_at=data["signed_at"],
    )
    leaf_idx = log.append(receipt)
```

Streaming doesn't change what's attested — it just lets you observe and route the attestation the moment it's signed, rather than discovering it after the run completes. See [Transparency log](transparency-log.md).
