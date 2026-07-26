# Killer benchmark appliance

Reproduce the killer demo from cold: Claudeway vs CrewAI vs single Claude on
a hard question, blind Sonnet judge, N runs. You bring an Anthropic API key;
`docker compose` handles the rest.

## Quickstart

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # required
docker compose up killer-bench             # builds, runs, writes the report
open benchmarks/out/killer_demo_results.md # or cat it
```

That's it. The `relay` service (`fiatjaf/nak serve`) starts in parallel for
the optional Nostr test path; `killer_demo.py` doesn't depend on it.

## What you get

`benchmarks/out/killer_demo_results.md` — the side-by-side report: wall-clock,
tokens, blind judge scores (correctness / nuance / completeness /
disagreement-surfaced), the per-agent Claudeway perspectives, and the signed
receipt. Same file the demo writes to `examples/`, staged into the volume.

## Knobs

| Env var | Default | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | _(required)_ | Drives the agent + judge calls |
| `KILLER_DEMO_RUNS` | `10` | Runs per approach. Lower for a smoke test |
| `CLAUDEWAY_TEST_RELAY` | `ws://relay:10547` | Optional; only for Nostr tests |

Smoke test in ~30s: `KILLER_DEMO_RUNS=1 docker compose up killer-bench`.

## Expected cost + runtime

- **Time:** ~5 min for the default 10 runs (Haiku agents, Sonnet judge).
- **API cost:** ~$0.50 in Haiku tokens + a few cents of Sonnet for the judge.
  Claudeway uses the most tokens (3 specialists + a debate revision round);
  single-Claude is the cheapest baseline.

## Without Docker

```bash
pip install -e ".[nostr,dev]" crewai 'litellm[proxy]'
export ANTHROPIC_API_KEY=sk-ant-...
python examples/killer_demo.py
```

## Troubleshooting

- **`ANTHROPIC_API_KEY must be set`** — compose rejected the empty value.
  Export it in the same shell that runs `docker compose up`.
- **Relay healthcheck fails** — the `relay` service builds `nak` from source
  on first run (~30s). `killer-bench` waits on it via `depends_on: healthy`.
- **Report missing from `benchmarks/out/`** — check the container log:
  `docker compose logs killer-bench`.
