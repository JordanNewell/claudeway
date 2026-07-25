# Buzz Adapter — Test Evidence

> Captured 2026-07-25 against coincurve 21.0.0 + fiatjaf/nak `serve` on
> `ws://localhost:10547`. Python 3.13.5 on Windows 11. Pytest 8.4.2.

The Buzz adapter ships only if four independent layers all pass. They do.

---

## 1. BIP-340 known-answer test (crypto correctness)

The signing code path was previously dead — it called `coincurve.schnorr_sign`,
an API that has never existed in any released coincurve. The fix routes through
`PrivateKey.sign_schnorr(msg, bytes(32))` (zero aux randomness → deterministic,
matches BIP-340 spec test vector 0).

```
pubkey expected: f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9
pubkey actual:   f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9
pubkey match:    True

sig expected: e907831f80848d1069a5371b402410364bdf1c5f8307b0084c55f1ce2dca821525f66a4a85ea8b71e482a74f382d2ce5ebeee8fdb2172f477df4900d310536c0
sig actual:   e907831f80848d1069a5371b402410364bdf1c5f8307b0084c55f1ce2dca821525f66a4a85ea8b71e482a74f382d2ce5ebeee8fdb2172f477df4900d310536c0
sig match:    True
```

---

## 2. Pytest suite (45 passing, 1 correctly skipped)

`CLAUDEWAY_TEST_RELAY=ws://localhost:10547 pytest tests/ -v`:

```
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-8.4.2, pluggy-1.6.0
plugins: anyio-4.14.2, dash-3.2.0, hypothesis-6.156.6, langsmith-0.4.10,
         asyncio-1.2.0, cov-7.0.0, snapshot-0.9.0
asyncio: mode=Mode.AUTO

tests/test_consensus.py .........
tests/test_coordinator.py ...........
tests/test_nostr.py ............
  - test_bip340_pubkey_matches_vector_0 PASSED
  - test_bip340_sign_matches_vector_0 PASSED
  - test_nostr_event_kind_is_nip78_addressable PASSED
  - test_nostr_event_id_is_sha256_of_nip01_serialization PASSED
  - test_nostr_event_pubkey_matches_xonly_derivation PASSED
  - test_nostr_event_signature_is_64_byte_schnorr PASSED
  - test_nostr_event_signature_covers_event_id PASSED
  - test_nostr_event_tags_include_d_tag_and_client PASSED
  - test_nostr_event_content_carries_signed_receipt PASSED
  - test_nostr_event_roundtrips_through_dict PASSED
  - test_nostr_event_publishes_and_reads_back PASSED   <-- integration, live relay
tests/test_signing.py .............s

======================== 45 passed, 1 skipped in 4.09s ========================
```

The skipped test is `test_nostr_transport_requires_optional_lib` — it asserts
`ImportError` when coincurve is absent, so it correctly skips when coincurve is
installed. Not a failure.

---

## 3. Independent third-party verifier (`nak verify`)

`nak` is fiatjaf's reference Nostr CLI (the canonical Go implementation, used
by Nostr clients and relays worldwide). Its `verify` subcommand checks both the
NIP-01 event-id hash and the BIP-340 Schnorr signature.

```
$ cat event.json | nak verify
$ echo $?
0
```

Per `nak verify --help`: _"it outputs nothing if the verification is
successful."_ Silent + exit 0 = the event Claudeway produced is spec-correct
Nostr that any relay/client will accept.

---

## 4. End-to-end demo (`examples/buzz_consensus_demo.py`)

Three agents reach consensus → receipt is signed (Ed25519) → wrapped as a NIP-78
Nostr event → published to `nak serve` → read back → receipt verified on the
read-back content.

```
Step 1 - three agents reach consensus
final: bootstrap
agreement: 78%
  - Operator (conf 0.85): bootstrap
  - Investor (conf 0.65): raise now
  - CFO (conf 0.78): bootstrap

Step 2 - sign the receipt (Ed25519)
algorithm: ed25519
public key: 25b12f2e9d...fdbec4 (truncated; demo value rotates per run)
signature: b6ae9381268a...6c45640c (truncated; same reason)

Step 3 - wrap as Nostr NIP-78 event
event id: f08a846928be5de3df94ee4baa3aa86045b3f4acae9c14630453d7516e6f7e89
kind:     30078 (NIP-78 addressable)

Step 4 - publish to relay (simulating a Buzz room)
relay accepted event with id f08a846928be5de3...
(relay acceptance == Schnorr signature verified per NIP-01)

Step 5 - Buzz room verifies the receipt
receipt signature valid: True
final answer (relayed): bootstrap
```

---

## Reproduction

```bash
# 1. install
pip install -e ".[nostr,dev]" websockets

# 2. stand up a reference relay (Go required)
go install github.com/fiatjaf/nak@latest
nak serve --port 10547 &

# 3. run the suite
CLAUDEWAY_TEST_RELAY=ws://localhost:10547 pytest tests/ -v

# 4. run the demo
python examples/buzz_consensus_demo.py
```
