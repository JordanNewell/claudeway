---
title: Transports — JSON, W3C VC, Nostr NIP-78
description: One signed ConsensusReceipt, three wire formats. Pick the one your downstream system already speaks.
---

# Transports

Signing ([`claudeway.signing`](api-reference.md#claudeway.signing)) is
**independent of transport**. A `ConsensusReceipt` is a canonical, signed
payload; the transports below render that *same* receipt into a wire format
downstream systems consume. Change transports without re-signing.

| Transport | Wire format | Where it lands | When to use |
|---|---|---|---|
| **JSON receipt** | Plain JSON | Files, logs, HTTP bodies, anything | Default. Simplest verifiable artifact. |
| **W3C Verifiable Credential** | VC v2.0 envelope | W3C-aligned identity/attestation systems | When the consumer follows W3C VC/DID conventions (the direction the [W3C AI Agent Protocol CG](https://www.w3.org/community/ai-agent-protocol/) is standardizing on). |
| **Nostr NIP-78 event** | `kind: 30078` addressable event, BIP-340 Schnorr signature | Any Nostr relay — including **Buzz rooms** | When consensus should land in a room agents already monitor. Buzz interop. |

---

## Why three

There is no single "right" wire format for an agent attestation. The W3C
community is converging on Verifiable Credentials for agent identity; Nostr
is the dominant open-protocol transport for real-time agent rooms; and a
plain JSON receipt is the lowest-common-denominator any system can ingest.

Hardwiring any one of these would force a rewrite. Claudeway's
`SignatureBackend` ABC signs the canonical payload once; each transport only
decides how that signed payload is wrapped for the wire.

---

## JSON receipt

The simplest verifiable artifact. `to_json_receipt` produces a self-contained
JSON document carrying the receipt payload, signature, and public key. Anyone
holding the document can verify integrity later.

```python
from claudeway.transports import to_json_receipt

doc = to_json_receipt(receipt)   # -> dict ready for json.dumps
```

Use this when:

- You're persisting receipts in a database, object store, or audit log.
- You're returning consensus over HTTP from your own service.
- You don't need to interop with W3C VC consumers or Nostr relays.

## W3C Verifiable Credential

Renders the signed receipt as a [W3C VC v2.0](https://www.w3.org/TR/vc-data-model-2.0/)-compatible
envelope. The receipt's payload becomes the credential subject; the
signature is referenced as the proof.

This is the format the **W3C AI Agent Protocol Community Group** is
standardizing on for agent attestation. If you're building on a W3C-aligned
identity stack (DIDs, verifiable credentials, presentation exchanges), this
is the transport that fits.

## Nostr NIP-78 event

Renders the signed receipt as a [NIP-78](https://github.com/nostr-protocol/nips/blob/master/78.md)
addressable application data event:

- **`kind: 30078`** — NIP-78 addressable app data.
- **BIP-340 Schnorr signature** over `sha256` of the NIP-01 event
  serialization, computed over secp256k1.
- **`content`** carries the signed JSON receipt — any Nostr client can decode
  and verify it.

```python
from claudeway.transports import to_nostr_event

event = to_nostr_event(receipt, private_key_hex=nostr_key, d_tag="room-42")
# event.kind == 30078
# event.sig is BIP-340 Schnorr
# publish to any Nostr relay
```

The events Claudeway produces verify clean under [`nak`](https://github.com/fiatjaf/nak)
(the reference Nostr CLI) and round-trip through `nak serve` — publish,
subscribe, read back, receipt signature still verifies. See
[`TESTLOG.md`](https://github.com/JordanNewell/claudeway/blob/main/TESTLOG.md)
for the four-layer evidence trail (BIP-340 KAT, test suite, `nak verify`,
end-to-end demo).

### Nostr requires an extra

The Nostr path needs secp256k1 + BIP-340 Schnorr, which requires a native
library. Install the extra:

```bash
pip install claudeway[nostr]
```

[`coincurve`](https://pypi.org/project/coincurve/) ships prebuilt wheels for
CPython 3.11–3.13 on Windows, Linux, and macOS. The import is lazy — `pip
install claudeway` (without the extra) stays lean and never touches
secp256k1.

---

## Designing your own transport

`to_json_receipt`, `to_verifiable_credential`, and `to_nostr_event` are
plain functions over a `ConsensusReceipt`. If you need a different wire
format (CBOR, a custom envelope, an internal protobuf), the pattern is:

1. Get the canonical payload via `receipt.payload` (already canonicalized
   for signing — don't re-serialize from scratch or you'll break signature
   verification).
2. Render it into your wire format.
3. Carry `receipt.signature` and `receipt.public_key` alongside so a
   downstream verifier can call `Ed25519Backend().verify_receipt(receipt)`.

The signing layer never has to change.
