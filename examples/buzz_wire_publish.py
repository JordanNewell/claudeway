"""
Buzz wire publish — one-shot. Generates a fresh Nostr keypair, runs a real
Claudeway consensus on a Buzz-relevant question, signs the receipt, publishes
to a public Nostr relay, and prints the viewer URL.

Output: a https://nostr.mom URL that anyone (incl.
Jack Dorsey / Block's Buzz team) can open to see the signed receipt.

Run with:
    ANTHROPIC_API_KEY=sk-ant-... py examples/buzz_wire_publish.py
"""

import asyncio
import json
import os
import secrets
import time

from claudeway import (
    AgentConfig,
    ConsensusReceipt,
    Debate,
    Ed25519Backend,
    Swarm,
    SwarmConfig,
    Task,
)
from claudeway.transports import to_nostr_event

RELAY_URLS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://offchain.pub",
    "wss://relay.snort.social",
    "wss://nostr.land",
    "wss://relay.primal.net",
    "wss://nostr.mom",
]
VIEWER_TEMPLATE = "https://nostr.mom/e/{event_id}"
QUESTION = (
    "Block shipped Buzz on 2026-07-21 as the room agents talk in, coordinating "
    "via workflows and agent memberships. For an agent ecosystem to actually "
    "produce verifiable agreement — not just parallel answers — what's the "
    "missing primitive, and what does the smallest credible shipping version of "
    "it look like in 2026?"
)


async def run_consensus() -> tuple:
    """Three Claudeway agents debate via Debate strategy.

    Returns (ConsensusResult, swarm_name, task_id).
    """
    swarm = Swarm(
        SwarmConfig(
            name="BuzzCoordinationGap",
            description=QUESTION,
            agents=[
                AgentConfig(
                    "ProtocolArchitect",
                    "Distributed systems engineer with Nostr + BIP-340 chops",
                    "You think in open protocols, signed events, and tamper-evident logs. "
                    "Buzz is a Nostr app; the missing primitive should compose with "
                    "NIP-01/78.",
                ),
                AgentConfig(
                    "AgentFrameworkLead",
                    "Ex-LangGraph/CrewAI engineer who has burned by shallow coordination",
                    "You've shipped multi-agent systems and seen coordination fail at the "
                    "consensus boundary, not the orchestration boundary. The primitive must "
                    "plug into existing frameworks.",
                ),
                AgentConfig(
                    "AcquiHireBuyer",
                    "Principal eng at a large platform evaluating build-vs-buy for this gap",
                    "You think about moats: what's acquirable vs weekend-rebuildable. The "
                    "primitive must be cryptographically defensible, not just 'agents voting.'",
                ),
            ],
        ),
        api_key=os.environ["ANTHROPIC_API_KEY"],
        consensus=Debate(),
    )
    task = Task(id="buzz-gap-1", description=QUESTION, input_data={})
    completed = await swarm.process(task)
    return completed.result, "BuzzCoordinationGap", "buzz-gap-1"


def fresh_nostr_keypair() -> tuple[str, str]:
    """Returns (priv_hex, npub_hex) — fresh keypair just for this publish."""
    priv = secrets.token_hex(32)
    return priv, priv  # npub derivation needs coincurve; hex priv is enough for to_nostr_event


async def publish_to_relay(event: dict) -> list[str]:
    """Try each relay in RELAY_URLS. Returns list of relay URLs that accepted the event."""
    import websockets

    accepted = []
    for url in RELAY_URLS:
        try:
            async with websockets.connect(url, max_size=2**20) as ws:
                await ws.send(json.dumps(["EVENT", event]))
                got_ok = False
                for _ in range(15):
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    except TimeoutError:
                        break
                    msg = json.loads(raw)
                    if msg[0] == "OK" and msg[1] == event["id"]:
                        if msg[2]:
                            accepted.append(url)
                            print(f"  [OK] accepted: {url}")
                        else:
                            reason = msg[3] if len(msg) > 3 else "no reason"
                            print(f"  [REJECT] {url} -- {reason}")
                        got_ok = True
                        break
                if not got_ok:
                    print(f"  [NORESP] {url}")
        except Exception as e:
            print(f"  [FAIL] {url} -- {type(e).__name__}: {e}")
    return accepted


async def main():
    print(f"relays: {', '.join(RELAY_URLS)}")
    print(f"question:\n  {QUESTION}\n")

    # 1. Generate fresh Nostr identity for this publish
    nostr_priv, _ = fresh_nostr_keypair()
    print(f"fresh nostr keypair generated (priv: {nostr_priv[:8]}...)")

    # 2. Run real consensus
    print("\nrunning 3-agent Debate consensus...")
    result, swarm_name, task_id = await run_consensus()
    print(f"\nfinal answer:\n  {result['final_answer'][:200]}...")
    print(f"\nagreement: {result['agreement']:.0%}")
    print(f"rounds: {result['rounds']}")
    for r in result["responses"]:
        print(f"  - {r['agent']} (conf {r['confidence']:.2f})")

    # 3. Build ConsensusResult object + sign with Ed25519
    from claudeway.consensus import ConsensusResult
    from claudeway.swarm import AgentResponse

    cr = ConsensusResult(
        final_answer=result["final_answer"],
        method=result["method"],
        agent_count=result["agent_count"],
        responses=[
            AgentResponse(agent_name=r["agent"], answer=r["answer"], confidence=r["confidence"])
            for r in result["responses"]
        ],
        agreement=result["agreement"],
        rounds=result["rounds"],
    )

    receipt = ConsensusReceipt.from_result(cr, swarm_name=swarm_name, task_id=task_id)
    backend = Ed25519Backend()
    ed_priv, ed_pub = backend.generate_keypair()
    backend.sign_receipt(receipt, ed_priv)
    print(f"\nreceipt signed (Ed25519, pubkey: {ed_pub[:16]}...)")

    # 4. Wrap as NIP-78 kind:30078 event signed with the fresh Nostr key
    event = to_nostr_event(
        receipt,
        private_key_hex=nostr_priv,
        created_at=int(time.time()),
        d_tag="claudeway-buzz-wire-v030",
    )
    event_dict = event.to_dict() if hasattr(event, "to_dict") else event
    print(f"\nnostr event id: {event_dict['id']}")
    print(f"pubkey: {event_dict['pubkey']}")
    print(f"kind: {event_dict['kind']} (NIP-78 addressable)")

    # 5. Persist the event JSON BEFORE publish attempt (so we have it regardless)
    out_path = "buzz_wire_event.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(event_dict, f, indent=2)
    print(f"\nevent persisted to: {out_path}")

    # 6. Publish to multiple relays
    print(f"\npublishing to {len(RELAY_URLS)} relays...")
    accepted = await publish_to_relay(event_dict)

    if not accepted:
        print("\nNO RELAY ACCEPTED — but event JSON is saved.")
        print("Publish manually with:  nak event --relay <relay> < buzz_wire_event.json")
        return

    print(f"\n=== ACCEPTED BY {len(accepted)} RELAY(S) ===")
    for url in accepted:
        print(f"  {url}")

    print("\n=== VIEWER URLS (share these) ===")
    print(f"nostr.mom:    {VIEWER_TEMPLATE.format(event_id=event_dict['id'])}")
    print(f"primal.net:   https://primal.net/e/{event_dict['id']}")
    print(f"damus:        https://damus.io/{event_dict['id']}")
    print(f"\nnostr URI:    nostr:nevent://{event_dict['id']}")


if __name__ == "__main__":
    asyncio.run(main())
