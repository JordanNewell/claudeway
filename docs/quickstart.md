---
title: Quick start
description: From zero to a signed consensus receipt in under two minutes.
---

# Quick start

**Goal:** run your first signed multi-agent consensus and verify it.

You need Python 3.11+ and an
[Anthropic API key](https://console.anthropic.com/settings/keys).

---

## 1. Install

```bash
pip install claudeway
```

Optional extras, only if you need them:

```bash
pip install claudeway[mcp]        # expose consensus as an MCP server
pip install claudeway[nostr]      # sign Nostr events (Buzz interop)
pip install claudeway[pq]         # ML-DSA-65 post-quantum signatures
pip install claudeway[langgraph]  # StateGraph adapter
pip install claudeway[maf]        # Microsoft Agent Framework adapter
pip install claudeway[crewai]     # CrewAI @tool + Flow adapter
```

## 2. Set your Anthropic key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## 3. Run your first swarm

Save as `hello.py`:

```python
import asyncio
from claudeway import AgentConfig, Swarm, SwarmConfig, Task

async def main():
    swarm = Swarm(SwarmConfig(
        name="HelloSwarm",
        agents=[
            AgentConfig("Optimist", "Optimist", "You argue the upside."),
            AgentConfig("Pessimist", "Pessimist", "You argue the risk."),
            AgentConfig("Synthesizer", "Synthesizer", "You reconcile both."),
        ],
    ))

    task = Task(
        id="q1",
        description="Should a 2-person startup take seed money or bootstrap?",
        input_data={},
    )
    result = await swarm.process(task)
    print(result.result["final_answer"])
    print(f"agreement: {result.result['agreement']:.0%}")

asyncio.run(main())
```

Run it:

```bash
python hello.py
```

Three Claude agents answer in parallel. The default `WeightedVote` consensus
picks the highest-confidence answer and reports the agreement score.

## 4. Sign the result

This is the defensible part — the answer becomes a tamper-evident
attestation anyone can verify later:

```python
from claudeway import ConsensusReceipt, Ed25519Backend

receipt = ConsensusReceipt.from_result(result, swarm_name="HelloSwarm", task_id="q1")
backend = Ed25519Backend()
private_key, public_key = backend.generate_keypair()  # persist in real use
backend.sign_receipt(receipt, private_key)

# Anyone, anywhere, can verify later:
assert backend.verify_receipt(receipt) is True
# Tamper with the answer and verification fails.
```

Want post-quantum signatures instead? Swap one line — see
[`claudeway.signing_pq`](api-reference.md) in the API reference.

## 5. Try a harder question

`WeightedVote` is the cheap default — one round, picks the highest-confidence
answer. For genuinely contested questions, switch to `Debate` so agents see
peers' answers and revise once:

```python
from claudeway import Swarm, WeightedVote, Debate

# Cheap default
swarm = Swarm(config, consensus=WeightedVote())

# Hard questions — revision round, early-exits when agents already agree
swarm = Swarm(config, consensus=Debate())
```

See [`examples/consensus_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/consensus_demo.py)
for the disagreement → resolution flow.

## 6. Run Claudeway as an MCP server (optional)

Any MCP-capable agent (Claude Code, Cursor, Goose) can call consensus as a
tool — no SDK to learn:

```bash
claudeway-mcp            # stdio — for Claude Code, Cursor
claudeway-mcp --http     # HTTP/SSE — for remote agents
```

See [MCP server](mcp-server.md) for tool schemas and integration examples.

---

## Next

- [Concepts](concepts.md) — Swarm, Agent, Task, Consensus, Receipt, SignatureBackend explained narratively.
- [Transports](transports.md) — JSON vs W3C VC vs Nostr NIP-78, and when to pick each.
- [Adapters](adapters.md) — Buzz, LangGraph, CrewAI, MAF integration paths.
- [API Reference](api-reference.md) — auto-generated from the source.
