---
title: Troubleshooting
description: What fails, why, and how to recover. Anthropic API errors, structured-output parsing, signature/tamper detection, missing extras, Nostr relay rejection, async→sync deadlock.
---

# Troubleshooting

What fails, why, and how to recover. The SDK ships **no `logging` module usage and no custom exception classes** — failures surface as stdlib exceptions (`ImportError`, `ValueError`, `IndexError`, `NotImplementedError`) or propagate raw from the Anthropic SDK. Observability is via `print()` at failure points. There is **no verbose / DEBUG flag**.

---

## Anthropic API failures

**Symptom:** `anthropic.RateLimitError` / `APIStatusError` / `APIConnectionError` propagates out of `await swarm.process(task)`.

**Root cause:** `Agent.think()` calls `self.client.messages.create(**kwargs)` with **no retry, no backoff, no timeout**. Per-agent calls run concurrently via `asyncio.gather(*coros, return_exceptions=True)`.

**Recovery:** depends on how many agents failed.

- **One agent fails, others succeed** — the exception is captured by `gather(return_exceptions=True)`, logged via `print(f"Agent {name} failed: {result}")`, and the failed agent is **skipped**. The swarm survives. Verified by `test_failed_agent_is_skipped_not_raised`.
- **All agents fail** — `responses == []`, consensus returns an empty `ConsensusResult(final_answer="", agent_count=0, agreement=0.0)`. **No exception raised.** Detect with:
  ```python
  if result.result["agent_count"] == 0:
      # all agents failed; handle
  ```
- **Invalid key** — `AsyncAnthropic` raises on first call; same gather-skip path applies. There is **no early auth check**.

---

## Structured output parse failure

**Symptom:** Agent answer comes back as raw text; `confidence` defaults to `0.5`.

**Root cause:** Model didn't emit `<answer>…</answer>` tags, or truncated mid-tag.

**Recovery:** `parse_structured_output()` is **tolerant by design** — three fallbacks, never raises:

- No tags → raw text becomes `answer`.
- Open-but-unclosed `<answer>` (small model + tight `max_tokens`) → takes everything after the opening tag.
- Missing `<confidence>`/`<reasoning>` → defaults to `0.5` / `""`; confidence clamped to `[0.0, 1.0]`.

Verified by `test_parse_tolerates_truncated_answer_tag`.

If you're seeing this often, raise `max_tokens` on the offending `AgentConfig` (default is 4096, but tight benchmarks often use 256).

---

## Signature / receipt tamper detection

**Symptom:** `SignatureBackend.verify_receipt(receipt)` returns `False`.

**Root cause:** verification returns `False` (never raises) for any of:

- Unsigned receipt
- Payload hash mismatch — re-hashing the payload detects post-signing tamper
- Wrong public key
- `InvalidSignature` from the crypto library
- Malformed hex (broad `except Exception: return False`)

Verified by `test_payload_tamper_invalidates_signature`, `test_signature_tamper_invalidates`, `test_wrong_public_key_rejects`, `test_payload_hash_mismatch_rejects` — mirrored for ML-DSA in `test_signing_pq.py`.

**Recovery:** treat any `False` as untrusted. Never display the answer as consensus. Re-issue or investigate. The signature doesn't tell you *what* changed, only *that* it did — diff the payload against a known-good copy.

---

## Optional-dependency ImportError

Three lazy imports raise clear install hints:

| Missing | Error | Install |
|---|---|---|
| `coincurve` (Nostr transport) | `ImportError("Nostr transport requires coincurve (BIP-340 Schnorr). Install with: pip install claudeway[nostr]")` | `pip install claudeway[nostr]` |
| `dilithium-py` (post-quantum backend) | `ImportError("ML-DSA-65 backend requires dilithium-py… pip install claudeway[pq]")` | `pip install claudeway[pq]` |
| `mcp` (MCP client) | `ImportError("MCP support requires the 'mcp' package… pip install claudeway[mcp]")` | `pip install claudeway[mcp]` |

---

## Nostr relay rejection

**Symptom:** Relay returns `["OK", id, false, "reason"]` or doesn't respond.

**Root cause:** event rejected (rate-limited, banned, malformed) or relay offline.

**Recovery:** the SDK only **builds** the event via `to_nostr_event` — it does **not publish**. The reference publisher at `examples/buzz_wire_publish.py` shows the pattern: try each relay, handle `TimeoutError` (5 s), print `[REJECT reason]` / `[NORESP]` / `[FAIL]`, return the list of accepting relays. Claim success only when ≥1 relay accepted.

Tamper detection at the relay boundary uses `nak verify` (the reference Nostr CLI). Without `nak`, content/sig tamper is caught by recomputing the event id — see `test_nostr_event_tamper_detected_without_nak`.

---

## Async→sync deadlock (CrewAI adapter)

**Symptom:** CrewAI tool call hangs forever.

**Root cause:** naive `run_coroutine_threadsafe + fut.result()` self-deadlocks when the caller is on the loop's own thread (pytest-asyncio, CrewAI's async runtime) — `fut.result()` blocks the thread that would run the coro.

**Recovery:** `_run_sync()` in `adapters/crewai.py` always spawns a **fresh daemon thread** with its own event loop and `asyncio.run(coro)`, then `t.join()`. Worker exceptions are re-raised in the caller.

**Never** replace this with loop reuse. If you're writing a custom adapter that wraps async Claudeway calls into a sync surface, copy the `_run_sync` pattern verbatim.

---

## Empty / invalid input

- Empty prompt to MAF executor → `ValueError("consensus executor received an empty prompt…")`.
- Empty prompt to LangGraph node → `ValueError("consensus node could not find a prompt…")`.
- Bad swarm_id to runtime → `ValueError(f"Swarm {swarm_id} not found")`.
- Out-of-range Merkle leaf → `IndexError(f"leaf_index {i} out of range…")`.

---

## Defensive patterns to copy

- **Cost-guarded early exit.** `Debate.resolve()` skips the 2nd round when `first_agreement >= agreement_threshold`. Verified by `test_debate_early_exits_when_agreement_is_high`.
- **Verify before trusting.** Always `verify_receipt()` before displaying; always `verify_inclusion()` against a published root before claiming a receipt was logged.
- **Verify before publishing.** `buzz_wire_publish.py` collects `accepted` relays before claiming success.
- **Observer isolation.** `on_event` callbacks run in `try/except`; a buggy observer can never change consensus outcome. Verified by `test_on_event_observer_error_does_not_kill_agent`. (Note: this also means observer bugs are silent — log aggressively inside your callback.)

---

## Known footguns

- **Agreement scoring is surface-form only.** Three agents with substantively-identical but differently-worded prose score ~33% disagreement, falsely triggering a Debate round. Tracked as `TODO(semantic-agreement)` in `consensus.py`.
- **No retry, no timeout, no circuit breaker** on Anthropic calls.
- **Coordinator dependency failures are silent.** Unresolvable sub-task dependencies are marked `failed` with `{"error": "unresolvable dependency"}` rather than hanging. Check `sub_results[id]` for `"error"` keys after `coordinate()`.
- **`max_task_tokens` declared but not enforced.** The field exists on `SwarmConfig`; no code path reads it.
- **`topology` is advisory only.** No code branches on it.
