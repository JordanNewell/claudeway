---
title: Benchmarks — Claudeway vs single Claude vs CrewAI
description: Same hard question, three approaches, blind LLM-judge scoring. The killer demo.
---

# Benchmarks

The marketing asset for the launch: one hard question, three approaches, same
model, blind judge.

> The reproducible run lives at
> [`examples/killer_demo.py`](https://github.com/JordanNewell/claudeway/blob/main/examples/killer_demo.py).
> The full output — including every agent's full response and the signed
> receipt — is at
> [`examples/killer_demo_results.md`](https://github.com/JordanNewell/claudeway/blob/main/examples/killer_demo_results.md).

---

## The question

> You're the largest shareholder of a bootstrapped B2B SaaS startup. State:
> $5M ARR, growing 8% MoM, 18 months of runway, no outside capital, 12-person
> team. Out of nowhere, Stripe offers an acqui-hire: $20M (4x current
> valuation), all-stock, 4-year vesting, your team stays intact, you become
> Stripe's Director of Payments Product. The board (you + two co-founders)
> is split. Recommend: take the deal or pass? No hedging — pick one.

Deliberately hard: genuinely contested outcome, high stakes, forces a
decision instead of a hedge. Single-model baselines collapse to a confident
"take it" without engaging the split.

## At a glance (mean over 3 runs each)

| Approach | Wall-clock | Tokens (sum) | Judge score (/20) |
|---|---:|---:|---:|
| **Claudeway Swarm** | 29.8s | 67,522 | **18** (17–19) |
| **CrewAI crew** | 43.7s | — | 13 (12–14) |
| **Single Claude** | 7.5s | 1,870 | 11 (10–12) |

- Same model for every agent: `claude-haiku-4-5-20251001`.
- Blind judge: `claude-sonnet-4-6`, scoring on correctness, nuance,
  completeness, disagreement-surfaced (1–5 each, 20 max). Judge does not know
  which approach produced which answer.
- Each approach run 3× (LLMs are non-deterministic). Score column is mean;
  range in parens.

## The honest takeaway

- **Quality.** Claudeway scored **+7/20** vs single Claude on average. The
  structural win is the multi-perspective format: the judge sees *how* each
  specialist reasoned, not just the verdict.
- **Cost.** Claudeway used ~36x the tokens of single Claude. That's the real
  tradeoff. For `$0.001` decisions, single Claude is right. For decisions
  where being wrong is expensive — this one is $20M+ — the token cost is
  rounding error.
- **What's free with Claudeway.** Per-agent outputs are auditable (you see
  *why* each specialist concluded what they did), the consensus is a signed
  tamper-evident receipt, and the whole thing drops into a Buzz room as a
  NIP-78 event with no extra work. None of the other approaches give you any
  of those.

## Claudeway's unique artifacts

Two things the other approaches don't produce at all:

1. **The disagreement, surfaced.** Three specialists, agreement score **33%**,
   `disagreed: True`. Each agent's full answer is visible — you can audit
   *why* the consensus landed where it did.
2. **The signed receipt.** Tamper-evident. Anyone can verify it later
   without trusting Claudeway:

   ```
   public_key:    19bd8a248f6201dacd163e2aa88333164ae1fc0a1de6300ab31433689e8daf7a
   signature:     bf039a74eb7af94be3b0ffce1185d9b53f9618fee61a0990f09fac1a396af462...
   payload_hash:  1209ec3b675782d046fdf7b56b2f0fd7597762806d6998237fdcf7c5f83bd1f3
   verified:      True
   ```

## Methodology

- All agent calls use the same model for fairness.
- **CrewAI** uses its default sequential process; each persona writes a
  report, then a synthesizer agent produces the final answer.
- **Claudeway** uses `Debate` — each persona answers, sees peer responses,
  and revises once. The signed receipt is a separate, free artifact.
- **Single-Claude** baseline is one direct call with the same prompt.
- The judge scores blindly.
- Latency is wall-clock from kickoff to final answer returned.
- Token counts are exact for single-Claude and Claudeway (captured from the
  Anthropic SDK `response.usage`). CrewAI's litellm callback capture is
  unreliable on Windows + litellm 1.18+; its token count is omitted. Use
  wall-clock + output length as proxies.

## Reproduce

```bash
pip install -e ".[nostr,dev]" crewai
export ANTHROPIC_API_KEY=sk-ant-...
python examples/killer_demo.py
```

## Benchmark design principles

Claudeway's benchmark philosophy (drawn from the broader agent benchmark
literature):

1. **Same model across approaches.** Disagreements come from perspective and
   process, not model capability. Don't compare Claudeway-on-Sonnet to
   CrewAI-on-Haiku.
2. **Run N times.** LLMs are non-deterministic. A single run is anecdote,
   not evidence.
3. **Blind judge.** If the judge knows which approach produced which answer,
   you're measuring the judge's priors, not the answer.
4. **Report the range, not just the mean.** Score variance is itself a
   signal of stability.
5. **Cost and quality, side by side.** A cheaper answer that's wrong is not
   a win. A better answer that costs 100x may not be worth it. Publish the
   Pareto, not just one axis.

For a deeper look at the multi-agent benchmark landscape (SWE-bench, GAIA,
AgentBench, MultiAgentBench) and where "verifiable consensus" fits — nobody
else benchmarks it as a primitive — see the killer demo results doc linked
above.
