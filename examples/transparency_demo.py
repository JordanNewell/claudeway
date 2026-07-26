"""
Consensus transparency log demo — the headline visual.

Three swarms reach consensus. Each result is appended to a transparency
log. The log root is published as a Nostr anchor event. Later, anyone —
without trusting Claudeway — can verify a specific receipt was in the
log, using only the receipt + an inclusion proof + the published root.

This is the README demo: Certificate Transparency for agent consensus,
made concrete.

Day 1 (this demo): Merkle log + NIP-78 Nostr anchor. Day 2 will add
Bitcoin anchoring via OpenTimestamps (NIP-3 kind:1040), turning
"tamper-evident" into "tamper-proof."

    pip install -e ".[nostr]"
    python examples/transparency_demo.py          # offline, no API key needed
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from claudeway.consensus import ConsensusResult  # noqa: E402
from claudeway.signing import ConsensusReceipt, Ed25519Backend  # noqa: E402
from claudeway.swarm import AgentResponse  # noqa: E402
from claudeway.transparency import TransparencyLog  # noqa: E402


def _receipt(swarm_name: str, task_id: str, answer: str) -> ConsensusReceipt:
    """Build + sign a receipt (offline; no real Claude needed for the demo)."""
    result = ConsensusResult(
        final_answer=answer,
        method="weighted_vote",
        agent_count=3,
        responses=[
            AgentResponse(agent_name="A", answer=answer, confidence=0.9),
            AgentResponse(agent_name="B", answer=answer, confidence=0.85),
            AgentResponse(agent_name="C", answer=answer, confidence=0.8),
        ],
        agreement=0.9,
        rounds=1,
        disagreed=False,
    )
    receipt = ConsensusReceipt.from_result(result, swarm_name=swarm_name, task_id=task_id)
    # A fresh key per run (a real deployment persists CLAUDEWAY_SIGNING_KEY).
    priv = os.environ.get("CLAUDEWAY_SIGNING_KEY") or Ed25519Backend().generate_keypair()[0]
    Ed25519Backend().sign_receipt(receipt, priv)
    return receipt


def main() -> None:
    # --- Step 1: three swarms reach consensus ---------------------------------
    print("=" * 70)
    print("Step 1 - three swarms reach consensus (simulated for the demo)")
    print("=" * 70)
    receipts = [
        _receipt("DbChoice", "task-1", "use sqlite"),
        _receipt("ArchReview", "task-2", "active-active Postgres"),
        _receipt("HirePanel", "task-3", "make an offer"),
    ]
    for r in receipts:
        print(f"  {r.payload['swarm']}/{r.payload['task_id']}: "
              f"'{r.payload['result']['final_answer']}'  sig={r.signature[:16]}...")

    # --- Step 2: append all three to the transparency log --------------------
    print()
    print("=" * 70)
    print("Step 2 - append all three to the transparency log")
    print("=" * 70)
    log = TransparencyLog(name="claudeway-canonical")
    for rc in receipts:
        idx = log.append(rc)
        print(f"  appended {rc.payload['task_id']} -> leaf {idx}")

    print()
    print(f"log size: {log.size}")
    print(f"log root: {log.root.hex()}")

    # --- Step 3: anchor the log to Nostr --------------------------------------
    print()
    print("=" * 70)
    print("Step 3 - publish the log root as a Nostr anchor event")
    print("=" * 70)
    from datetime import datetime

    from claudeway.transports import to_log_anchor_event

    # A 32-byte Nostr key. In production, the canonical Claudeway log lives
    # under a Claudeway-published key; anyone can run their own log under
    # their own key.
    nostr_key = "0b" * 32
    anchor_event = to_log_anchor_event(
        # LogAnchor is built inline here for brevity; in real use, log.anchor()
        # would return one.
        type("LogAnchor", (), {
            "to_dict": lambda self: {
                "type": "claudeway.transparency.anchor.v1",
                "log_name": log.name,
                "tree_size": log.size,
                "root": log.root.hex(),
                "published_at": datetime.utcnow().isoformat(),
                "nostr_event_id": None,
            },
        })(),
        private_key_hex=nostr_key,
        log_name=log.name,
    )
    print(f"  Nostr event id: {anchor_event.id}")
    print(f"  kind: {anchor_event.kind} (NIP-78 addressable)")
    print(f"  d-tag: {[t for t in anchor_event.tags if t[0] == 'd'][0]}")
    print("  (in production: publish to a Nostr relay — the event stream IS")
    print("   the log's auditable history)")

    # --- Step 4: third-party verification ------------------------------------
    print()
    print("=" * 70)
    print("Step 4 - third party verifies a receipt was in the log")
    print("=" * 70)
    print("(No Claudeway trust required: receipt + proof + published root)")
    print()

    # A third party has: a specific receipt they care about (task-2), an
    # inclusion proof, and the published root. No TransparencyLog instance.
    target_receipt = receipts[1]
    proof = log.inclusion_proof(1)

    print(f"  receipt:    {target_receipt.payload['task_id']} "
          f"('{target_receipt.payload['result']['final_answer']}')")
    print(f"  proof:      leaf_index={proof.leaf_index} tree_size={proof.tree_size} "
          f"path_len={len(proof.audit_path)}")
    print(f"  root:       {log.root.hex()}")
    print()
    ok = TransparencyLog.verify_inclusion(target_receipt, proof, log.root)
    print(f"  verified:   {ok}")

    # --- Step 5: tamper detection --------------------------------------------
    print()
    print("=" * 70)
    print("Step 5 - tamper detection")
    print("=" * 70)
    tampered = _receipt("ArchReview", "task-2", "use mongodb instead")  # different answer
    caught = not TransparencyLog.verify_inclusion(tampered, proof, log.root)
    print(f"  tampered receipt ('use mongodb instead') correctly REJECTED: {caught}")

    # Final: what this means
    print()
    print("=" * 70)
    print("The upshot")
    print("=" * 70)
    print("Today Claudeway signs receipts — anyone can verify the signature,")
    print("but you have to trust Claudeway to *show you* the receipt.")
    print()
    print("After this: Claudeway's published log root commits to every receipt")
    print("ever issued. A receipt that was secretly altered, or quietly removed,")
    print("leaves a detectable gap in the log. Anyone — without trusting")
    print("Claudeway — can confirm a receipt was in the log at a given root.")
    print()
    print("Day 2 anchors each root to Bitcoin via OpenTimestamps (NIP-3),")
    print("turning 'tamper-evident' into 'tamper-proof.'")


if __name__ == "__main__":
    # The empty-log root reference (sanity):
    assert TransparencyLog().root == hashlib.sha256(b"").digest()
    main()
