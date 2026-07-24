# Claudeway — Quick Start

From zero to a signed consensus answer in under 2 minutes.

## 1. Install

```bash
pip install claudeway
# optional extras:
pip install claudeway[mcp]      # run consensus as an MCP server
pip install claudeway[nostr]    # sign Nostr events for Buzz interop
```

## 2. Set your Anthropic key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## 3. Run your first swarm (Python SDK)

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

```bash
python hello.py
```

## 4. Sign the result (the defensible part)

```python
from claudeway import ConsensusReceipt, Ed25519Backend

receipt = ConsensusReceipt.from_result(result, swarm_name="HelloSwarm", task_id="q1")
backend = Ed25519Backend()
private_key, public_key = backend.generate_keypair()  # persist in real use
backend.sign_receipt(receipt, private_key)

# Anyone can verify it later:
assert backend.verify_receipt(receipt) is True
# Tamper with the answer and verification fails.
```

## 5. Run Claudeway as an MCP server

Let any MCP-capable agent (Claude Code, Cursor, Goose, Buzz) call consensus as a tool:

```bash
claudeway-mcp            # stdio (local agents)
claudeway-mcp --http     # HTTP/SSE (remote agents, default port 8765)
```

The exposed tools:
- `reach_consensus(question, specialists, strategy)` → signed receipt
- `verify_consensus(receipt)` → `{"valid": true/false}`

## 6. Try the examples

```bash
git clone https://github.com/JordanNewell/claudeway
cd claudeway

python examples/quickstart.py        # 15-line minimal swarm
python examples/consensus_demo.py    # the killer demo: disagreement -> Debate
python examples/coordinator_demo.py  # hierarchical decomposition
```

## Next

- [README](README.md) — the full pitch + competitive positioning
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — design and internals
- [docs/DEPRECATION.md](docs/DEPRECATION.md) — why multi-tenant/billing is deferred
