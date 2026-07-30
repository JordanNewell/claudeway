"""
Buzz adapter demo - the flip-play showcase.

Three Claudeway agents reach signed consensus on a hard question. The signed
receipt is wrapped as a Nostr NIP-78 event and published to a relay. A
simulated subscriber reads the event back and verifies the consensus
signature in one line.

This is what shows Block that Claudeway is the consensus layer Buzz doesn't
ship (Block shipped Buzz 2026-07-21 with workflow coordination - Claudeway
adds the cryptographic consensus primitive, and the receipts are verifiable
forever).

    # terminal 1 - stand up a local relay
    nak serve --port 10547

    # terminal 2 - run the demo (offline mode, no Anthropic key needed)
    python examples/buzz_consensus_demo.py

    # or with real Claude agents
    ANTHROPIC_API_KEY=sk-ant-... python examples/buzz_consensus_demo.py

Requires: pip install claudeway[nostr] websockets
"""

import asyncio
import json
import os
import time
from typing import Any

from claudeway.consensus import ConsensusResult
from claudeway.signing import ConsensusReceipt, Ed25519Backend
from claudeway.swarm import AgentResponse
from claudeway.transports import to_nostr_event

RELAY_URL = os.environ.get("CLAUDEWAY_DEMO_RELAY", "ws://localhost:10547")
# Deterministic Nostr identity for the demo (NOT the receipt signing key -
# by design, the relay key can rotate without invalidating receipts).
DEMO_NOSTR_SECRET = "ab" * 32

QUESTION = (
    "A startup hits PMF and has 6 months of runway. Raise at a $20M cap now, "
    "or bootstrap another 6 months and raise at $50M with stronger numbers?"
)


def mock_consensus() -> ConsensusResult:
    """Offline-mode consensus: three advisors, weighted-vote, no API calls."""
    responses = [
        AgentResponse(agent_name="Operator", answer="bootstrap", confidence=0.85),
        AgentResponse(agent_name="Investor", answer="raise now", confidence=0.65),
        AgentResponse(agent_name="CFO", answer="bootstrap", confidence=0.78),
    ]
    # 2 of 3 say bootstrap with high confidence -> weighted vote lands there.
    return ConsensusResult(
        final_answer="bootstrap",
        method="weighted_vote",
        agent_count=3,
        responses=responses,
        agreement=0.78,
        rounds=1,
    )


async def real_consensus() -> ConsensusResult:
    """Online mode: real Claude agents debate via Claudeway's Swarm."""
    from claudeway import AgentConfig, Swarm, SwarmConfig, Task, WeightedVote

    swarm = Swarm(
        SwarmConfig(
            name="RunwayDecision",
            description=QUESTION,
            agents=[
                AgentConfig("Operator", "Founder", "Bias toward control and runway."),
                AgentConfig("Investor", "VC", "Bias toward momentum and speed."),
                AgentConfig("CFO", "CFO", "Bias toward financial discipline."),
            ],
        ),
        api_key=os.environ["ANTHROPIC_API_KEY"],
        consensus=WeightedVote(),
    )
    completed = await swarm.process(Task(id="runway-1", description=QUESTION, input_data={}))
    r = completed.result
    return ConsensusResult(
        final_answer=r["final_answer"],
        method=r["method"],
        agent_count=r["agent_count"],
        responses=[
            AgentResponse(agent_name=resp["agent"], answer=resp["answer"],
                          confidence=resp["confidence"])
            for resp in r["responses"]
        ],
        agreement=r["agreement"],
        rounds=r["rounds"],
    )


def header(s: str) -> None:
    print(f"\n{'=' * 70}\n{s}\n{'=' * 70}")


async def publish_and_subscribe(event_payload: dict[str, Any]) -> dict[str, Any]:
    """Publish the event to a relay, then subscribe and read it back.

    Implements the NIP-01 wire protocol directly so the demo has zero
    Nostr-specific dependencies beyond `websockets`. A real Claudeway user
    would use pynostr / nostr-sdk / etc. — or the Buzz client itself.
    """
    import websockets

    async with websockets.connect(RELAY_URL) as ws:
        # Publish.
        await ws.send(json.dumps(["EVENT", event_payload]))
        # Drain until we get our OK.
        for _ in range(5):
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            msg = json.loads(raw)
            if msg[0] == "OK" and msg[1] == event_payload["id"]:
                if not msg[2]:
                    raise RuntimeError(f"relay rejected event: {msg[3]}")
                break

        # Subscribe to kind-30078 from ourselves.
        sub_id = "claudeway-buzz-demo"
        await ws.send(json.dumps([
            "REQ", sub_id,
            {"kinds": [30078], "authors": [event_payload["pubkey"]], "limit": 1},
        ]))
        seen = None
        for _ in range(10):
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            msg = json.loads(raw)
            if msg[0] == "EVENT" and msg[1] == sub_id:
                seen = msg[2]
                break
        await ws.send(json.dumps(["CLOSE", sub_id]))

    if seen is None:
        raise RuntimeError("did not receive our own event back from the relay")
    return seen


async def main() -> None:
    use_real = bool(os.environ.get("ANTHROPIC_API_KEY"))
    header(f"Claudeway x Buzz - consensus with signed Nostr events"
           f"\n({'real Claude agents' if use_real else 'offline mock agents'})")
    print(f"relay: {RELAY_URL}")
    print(f"question: {QUESTION}")

    # 1. Agents reach consensus.
    header("Step 1 - three agents reach consensus")
    result = await real_consensus() if use_real else mock_consensus()
    print(f"final: {result.final_answer}")
    print(f"agreement: {result.agreement:.0%}")
    for r in result.responses:
        print(f"  - {r.agent_name} (conf {r.confidence:.2f}): {r.answer}")

    # 2. Sign the receipt (Ed25519 - tamper-evident).
    header("Step 2 - sign the receipt (Ed25519)")
    receipt = ConsensusReceipt.from_result(
        result, swarm_name="RunwayDecision", task_id="runway-1"
    )
    backend = Ed25519Backend()
    priv, pub = backend.generate_keypair()
    backend.sign_receipt(receipt, priv)
    print(f"algorithm: {receipt.algorithm}")
    print(f"public key: {pub}")
    print(f"signature: {receipt.signature}")
    print(f"payload hash: {receipt.payload_hash}")

    # 3. Wrap as a Nostr NIP-78 kind-30078 event and sign with the relay key.
    header("Step 3 - wrap as Nostr NIP-78 event")
    event = to_nostr_event(
        receipt,
        private_key_hex=DEMO_NOSTR_SECRET,
        created_at=int(time.time()),
        d_tag="claudeway-buzz-room-runway",
    )
    print(f"event id: {event.id}")
    print(f"pubkey:   {event.pubkey}")
    print(f"kind:     {event.kind} (NIP-78 addressable)")
    print(f"sig:      {event.sig}")
    print(f"tags:     {event.tags}")

    # 4. Publish to the relay (any Nostr subscriber can read it back).
    header("Step 4 - publish to relay (simulating a Nostr subscriber)")
    try:
        seen = await publish_and_subscribe(event.to_dict())
    except (OSError, ConnectionRefusedError) as e:
        print(f"\nCould not connect to relay at {RELAY_URL}: {e}")
        print("Start one with:  nak serve --port 10547")
        print("(or install nak:  go install github.com/fiatjaf/nak@latest)")
        print("\nThe event was constructed correctly - run `nak verify` on:")
        print(json.dumps(event.to_dict()))
        return

    print(f"relay accepted event with id {seen['id'][:16]}...")
    print("(relay acceptance == Schnorr signature verified per NIP-01)")

    # 5. Verify the consensus receipt on the read-back content.
    header("Step 5 - subscriber verifies the receipt")
    payload = json.loads(seen["content"])
    rebuilt = ConsensusReceipt(
        payload=payload["payload"],
        algorithm=payload["algorithm"],
        public_key=payload["public_key"],
        signature=payload["signature"],
        payload_hash=payload["payload_hash"],
        signed_at=payload["signed_at"],
    )
    ok = Ed25519Backend().verify_receipt(rebuilt)
    print(f"receipt signature valid: {ok}")
    print(f"final answer (relayed): {payload['payload']['result']['final_answer']}")

    header("Done")
    print("The same event lands in any Nostr client subscribed to this relay.")
    print("Tamper with one byte and the receipt signature fails - that's the moat.")
    print("\nFull event JSON (paste into any Nostr client):")
    print(json.dumps(seen, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
