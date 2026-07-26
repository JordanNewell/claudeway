# Security Policy

## Reporting a Vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Report vulnerabilities privately to **<security@jordannewell.com>**.
(Placeholder address — Jordan will replace with a dedicated security inbox
before the v0.3.0 release tag.)

If you have a PGP key, encrypt the report. The fingerprint of the project's
reporting key will be published here once Jordan generates it:

```
PGP fingerprint:  TBD (to be published)
PGP public key:   TBD (to be published)
```

Until the PGP key is published, plaintext email is fine — but please prefer
it over GitHub issues either way.

Please include, where possible:

- A description of the issue and its impact.
- The smallest reproducer you can manage (a failing test is ideal).
- Affected versions (or the commit SHA you tested against).
- Any mitigations you've already tried.

## Response SLA

- **Acknowledgement:** within **48 hours** (typically same business day).
- **Initial assessment + severity rating:** within **5 business days**.
- **Fix or mitigation timeline** depends on severity:
  - *Critical* (RCE, signature forgery, key compromise): patch or mitigation
    within 7 days of confirmation; coordinated disclosure afterwards.
  - *High* (auth bypass, receipt tampering under specific conditions): patch
    within 30 days.
  - *Medium / Low:* next minor release.

We will keep you informed at each step and credit you in the release notes
unless you'd prefer to remain anonymous.

## Scope

**In scope:**

- The `claudeway` Python package (everything under `claudeway/`).
- The adapters (`claudeway.adapters.*`).
- The MCP server (`claudeway.server`).
- The signature and transports layer — particularly anything that could
  break signature verification or canonical serialization.

**Out of scope:**

- Vulnerabilities in third-party dependencies. Report those upstream
  (Anthropic SDK, `cryptography`, `coincurve`, `langgraph`, `mcp`, etc.).
  We bump deps as fixes ship, but we don't own their CVEs.
- The single-tenant runner and Next.js dashboard. These are deferred
  ([`docs/DEPRECATION.md`](docs/DEPRECATION.md)) and not shipped in the SDK
  wheel; we still want to hear about issues in them, but they are not held
  to the same SLA as the SDK.
- Attacks requiring a compromised maintainer, a compromised signing key, or
  physical access to the reporter's machine.
- Reports from automated scanners without a working reproducer.

## Threat model

See [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md) for the full threat
model — what Claudeway's signatures are and aren't designed to prove,
which components are trusted, and what an attacker controlling each
component can and cannot do.

The short version: a `ConsensusReceipt` proves **a particular consensus
result was produced and signed by a particular key**. It does not prove the
key belongs to a specific identity (that's a DID/identity concern, layered
on top), and it does not prove the underlying Claude calls were honest
(that's a model-behavior concern, not a signature concern). Don't use
receipts as a substitute for either.

## Disclosure policy

We follow **coordinated disclosure**. Once a fix is available we'll publish
a GitHub Security Advisory, request a CVE if appropriate, cut a patch
release, and credit the reporter in the changelog. We will not publish
details of unpatched critical issues.
