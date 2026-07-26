# Claudeway killer benchmark appliance.
#
# Reproduces examples/killer_demo.py from cold. The reviewer brings only an
# Anthropic API key; this image carries every system dep (Python 3.13,
# claudeway[benchmark,nostr], crewai, litellm) so `docker compose up
# killer-bench` lands a report in benchmarks/out/.
#
# Single stage: a multi-stage split saves <40MB here (the cost is crewai's
# dependency tree, all of it runtime-needed), and a single stage keeps the
# image rebuildable on a reviewer's laptop in one pass.

FROM python:3.13-slim

# Compiler toolchain + ca certs: cryptography, coincurve, and several
# transitive deps of crewai/litellm build wheels at install time on slim
# images. git is needed for `pip install -e .` to resolve the local tree.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the source so the editable install resolves. The COPY ordering puts
# the heavy pip layer (below) after these COPYs; changing pyproject.toml or
# the package source invalidates it, but that's the right tradeoff — the
# install needs the tree present.
COPY pyproject.toml README.md LICENSE ./
COPY claudeway ./claudeway
COPY examples ./examples

# Install only what the demo needs at runtime: [benchmark] pulls crewai +
# litellm, [nostr] pulls coincurve (the demo signs a receipt). We skip
# [dev] (pytest/mypy/ruff/build) — a reviewer reproducing the demo doesn't
# run tests, and dropping it keeps the image under 500MB. The [benchmark]
# extra already provides base litellm; we avoid litellm[proxy] because its
# dep tree backtracks for minutes and pulls a proxy stack the demo never
# imports (the demo only uses litellm.success_callback, a base API).
RUN pip install --no-cache-dir -e ".[benchmark,nostr]"

# Where the report lands. Mounted as a named volume in docker-compose so the
# reviewer's host sees killer_demo_results.md without a rebuild.
RUN mkdir -p /app/benchmarks/out
VOLUME /app/benchmarks/out

# The entrypoint validates the API key, points CLAUDEWAY_TEST_RELAY at the
# relay service, runs the demo, then copies the hardcoded report path next
# to the script out to the mounted volume.
COPY benchmarks/run.sh /app/benchmarks/run.sh
RUN chmod +x /app/benchmarks/run.sh

ENTRYPOINT ["/app/benchmarks/run.sh"]
