#!/usr/bin/env bash
# Killer benchmark entrypoint.
#
# Validates the reviewer's API key is set, points the (optional) Nostr test
# relay env at the compose `relay` service, runs examples/killer_demo.py,
# then copies the report the demo hardcodes next to the script out to the
# mounted volume so it's visible on the host.
set -euo pipefail

# --- Preflight --------------------------------------------------------------

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    cat >&2 <<'EOF'
ERROR: ANTHROPIC_API_KEY is not set.

The killer demo makes real Claude calls (Haiku agents + a Sonnet judge).
Export it before running docker compose:

    export ANTHROPIC_API_KEY=sk-ant-...
    docker compose up killer-bench

EOF
    exit 2
fi

# The relay service is reachable at `relay:10547` from inside the compose
# network. killer_demo.py itself doesn't use the relay, but the env is here
# for the test suite and the buzz demo if a reviewer runs them in the same
# container. Harmless no-op for the killer demo.
export CLAUDEWAY_TEST_RELAY="${CLAUDEWAY_TEST_RELAY:-ws://relay:10547}"

# How many runs per approach. Default 10 for a stable mean; override for a
# faster smoke test (KILLER_DEMO_RUNS=1).
export KILLER_DEMO_RUNS="${KILLER_DEMO_RUNS:-10}"

echo "=== Claudeway killer benchmark ==="
echo "ANTHROPIC_API_KEY: set (len ${#ANTHROPIC_API_KEY})"
echo "KILLER_DEMO_RUNS:  ${KILLER_DEMO_RUNS}"
echo "Relay:             ${CLAUDEWAY_TEST_RELAY} (optional, for Nostr tests)"
echo

# --- Run --------------------------------------------------------------------

cd /app
python examples/killer_demo.py

# --- Stage the report -------------------------------------------------------
#
# killer_demo.py writes the report to examples/killer_demo_results.md
# (hardcoded relative to the script). Copy it to the mounted volume so the
# host can read it without docker cp. Keep the original in place too, so a
# reviewer poking around the container finds it where the demo left it.

OUT_DIR="/app/benchmarks/out"
mkdir -p "${OUT_DIR}"

if [ -f examples/killer_demo_results.md ]; then
    cp examples/killer_demo_results.md "${OUT_DIR}/killer_demo_results.md"
    echo
    echo "=== Report ready ==="
    echo "Host path:   $(pwd)/benchmarks/out/killer_demo_results.md"
    echo "             (mounted from the compose 'benchmarks-out' volume)"
    echo "Container:   /app/examples/killer_demo_results.md"
else
    echo "WARNING: examples/killer_demo_results.md was not written." >&2
    echo "         The demo may have failed; check the log above." >&2
    exit 1
fi
