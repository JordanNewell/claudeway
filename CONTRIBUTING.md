# Contributing to Claudeway

Thanks for considering a contribution. Claudeway is a small, opinionated
project; this doc exists so pull requests land cleanly and reviewers can
move fast.

## Quick start

```bash
git clone https://github.com/JordanNewell/claudeway.git
cd claudeway
pip install -e ".[mcp,nostr,dev]"
pytest tests/ -v
ruff check claudeway/ tests/ examples/
```

Set `ANTHROPIC_API_KEY` to run the examples or any live test:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python examples/quickstart.py
```

## Project layout

| Path | Purpose |
|---|---|
| `claudeway/` | The shipped SDK package. Lean by design — keep new deps out of the base install. |
| `claudeway/adapters/` | Optional integrations (LangGraph). Lazy-import the host framework. |
| `claudeway/tools/` | Tool layer used by `Agent`. MCP tools import lazily. |
| `examples/` | Runnable demos. `killer_demo.py` is the benchmark — don't break it. |
| `tests/` | Pytest suite. Async tests use `pytest-asyncio` in auto mode. |
| `docs/` | The mkdocs-material site (`mkdocs.yml` at repo root). |
| `api/`, `dashboard/`, `infra/` | Deferred single-tenant runner. See `docs/DEPRECATION.md`. Don't add features here. |

## Before you open a PR

1. **Open an issue first for non-trivial changes.** A 30-second heads-up
   saves everyone from a PR that's the wrong shape. Bug fixes and doc
   tweaks can go straight to PR.
2. **Branch from `main`.** One logical change per PR.
3. **Conventional commits.** `feat:`, `fix:`, `docs:`, `test:`, `refactor:`,
   `chore:`, `ci:`. Subject ≤72 chars. Body wraps at 80. Explain the *why*
   when it's non-obvious. Match the existing log:
   `git log --oneline -20`.
4. **Keep the base install lean.** New runtime dependencies in `claudeway/`
   (outside `adapters/`) need a strong justification. Prefer an optional
   extra, lazy imports, or stdlib.
5. **Don't add features beyond what was asked.** No drive-by refactors,
   docstrings, or type annotations on code you didn't touch. Delete unused
   code; don't leave backwards-compat hacks.

## Code style

- `ruff` is the only formatter/linter. Config in `pyproject.toml`. It runs
  on `claudeway/`, `tests/`, and `examples/` in CI.
- Python 3.11 minimum. Use modern syntax (`from __future__ import
  annotations` where it makes sense).
- Match the surrounding file. If the file uses dataclasses, use dataclasses;
  if it uses Pydantic, use Pydantic.

## Tests

- Add or update tests for any behavior change in `claudeway/`.
- Live tests (anything that calls the real Anthropic API or a real Nostr
  relay) must be **opt-in** via an env var. See
  `tests/test_langgraph_adapter.py` for the pattern:
  `CLAUDEWAY_TEST_LANGGRAPH=1` to enable. The default `pytest tests/` run
  must work offline with no API keys.
- For the Nostr relay integration test, set `CLAUDEWAY_TEST_RELAY=ws://...`
  pointing at a relay (`nak serve` works locally).

## Docs

The docs site is mkdocs-material with mkdocstrings. API references are
auto-generated from module/class docstrings — if you change a public API,
update the docstring and the reference page updates on the next build.

```bash
pip install -e ".[docs]"
mkdocs serve        # live preview at http://127.0.0.1:8000
mkdocs build        # strict build into site/
```

`docs/` pages are Markdown. The site auto-deploys to GitHub Pages on push to
`main` via `.github/workflows/docs.yml`.

## The killer demo

`examples/killer_demo.py` is the marketing asset — same question, single
Claude vs CrewAI vs Claudeway, blind judge. Treat its output as load-bearing:

- Don't change the model or prompt without re-running all three approaches
  3× and updating `examples/killer_demo_results.md`.
- Don't make changes that regress the judge score. Quality wins are the
  entire point.

## Security reports

Found a security issue? **Do not open a public issue.** See
[SECURITY.md](SECURITY.md) for the private reporting process and SLA.

## Commit message rules (hard rules)

- Conventional commits, subject ≤72 chars, body wraps at 80.
- **No `Co-Authored-By: Claude` or any AI-attribution trailer.** Tools
  don't get authorship credit; humans do. The pre-push hook rejects these.
- **Never use `--no-verify` with `git commit` or `git push`.** The local
  hook harness is the last line of defense against leaked secrets and AI
  trailers. If a hook fails, fix the underlying issue or add an inline
  `# gitleaks:allow` comment for verified false positives — don't bypass.

## Releases

Releases are tagged by the maintainer (Jordan) — don't tag in a PR. Bump
the version in both `pyproject.toml` and `claudeway/__init__.py`, update
`docs/CHANGELOG.md`, and the maintainer will tag and (eventually) publish
to PyPI.

## Code of conduct

Participation in this project is governed by the
[Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By
participating you agree to abide by its terms.
