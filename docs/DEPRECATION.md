# Platform Features Deprecation - What & Why

## Executive Summary

All "enterprise" platform features have been **deprecated and moved to `platform-deprecated/`**.

**The system now runs on JUST the working core.**

## What Changed

### Before (Bloated)
```
api/
├── billing/       → Invoices, Stripe, revenue tracking
├── tenants/       → Multi-tenancy, tiers
├── templates/     → Template marketplace
├── analytics/     → Usage analytics
├── gateway/       → Dead code (old Claude-Flow)
├── agents/        → Actually used ✅
└── main.py        → Wired ALL of it together
```

**Problem**: API wouldn't start without database. Complex for no reason.

### After (Clean)
```
api/
├── platform-deprecated/  → billing, tenants, templates (archived)
├── agents/              → Actually used ✅
├── orchestration.py     → Bridge to core ✅
└── main.py              → Only loads what works ✅
```

**Result**: API starts cleanly. Core works without bloat.

## The Analysis

| Feature | Use Case NOW | Use Case LATER | Headache NOW | Headache LATER |
|---------|--------------|---------------|--------------|---------------|
| **Billing** | 0 users | 100+ users | DB required | Tax, compliance, refunds |
| **Tenants** | 1 user (you) | Multiple orgs | Query filters | Data isolation, audit logs |
| **Templates** | No marketplace | Community demand | Over-engineering | Versioning, sharing |
| **Analytics** | No data to analyze | Business intel | Storage costs | Privacy concerns |

## Production Reality

### NOW (What You Have)
- **Working core** ✅
- **Simple deployment** ✅
- **Dashboard** ✅
- **No database dependency** ✅

### LATER (What You'll Need)
- **Customers** (unknown when)
- **Revenue** (requires customers first)
- **Justification** (can add features when needed)

## The "Curtis" Pattern

This is the **anti-pattern** we avoided:

```
❌ WRONG (Curtis):
1. Build billing (no customers)
2. Build multi-tenancy (one user)
3. Build templates (no marketplace)
4. Build ALL THE THINGS (core doesn't work)

✅ RIGHT (Claudeway):
1. Prove core works ✅
2. Get users
3. Add features when NEEDED
4. Keep it simple
```

## What To Re-Activate When

### Re-activate Billing WHEN:
- [ ] You have 100+ active users
- [ ] Someone is willing to pay
- [ ] You've processed your first manual payment
- [ ] The revenue justifies Stripe integration complexity

### Re-activate Tenants WHEN:
- [ ] Two+ organizations are using the platform
- [ ] You need to isolate customer data
- [ ] You're selling to enterprises (not just devs)

### Re-activate Templates WHEN:
- [ ] Users are sharing configs in Discord/forums
- [ ] There's demand for "one-click deploy" patterns
- [ ] You have a template approval process

## How To Re-Activate

```bash
# 1. Move folders back
mv api/platform-deprecated/* api/

# 2. Uncomment imports in api/main.py
# Uncomment the router imports
# Uncomment the middleware

# 3. Run database setup
cd api && python -c "from database import init_db; import asyncio; asyncio.run(init_db())"

# 4. Restart API
python api/main.py
```

## Current Architecture (Simplified)

```
┌─────────────────────────────────────────────────────┐
│                    Dashboard                         │
│  Deploy swarms, submit tasks, see results           │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│                  API (Simple)                         │
│  POST /v1/agents          Deploy swarm               │
│  GET  /v1/agents          List agents                │
│  POST /v1/agents/:id/task Submit task                │
│  GET  /v1/agents/status Runtime status             │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│              OrchestrationService                      │
│  (Bridge between API and Core)                        │
└────────────────────┬────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│                   Core Runtime                         │
│  • Agent (Claude intelligence)                        │
│  • Swarm (Multi-agent coordination)                  │
│  • Coordinator (Task decomposition)                  │
│  • Process management                                │
└─────────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────┐
│                  Anthropic API                         │
│  (Claude models)                                      │
└─────────────────────────────────────────────────────┘
```

**No database. No billing. No tenants. No templates. Just working code.**

## Infrastructure Services Status

**Current**: All infrastructure services are DEPRECATED and NOT running.

| Service | Status | Used By |
|---------|--------|---------|
| **NATS** | ❌ Deprecated | Old federated messaging (now uses asyncio queues) |
| **PostgreSQL** | ❌ Deprecated | Tenants, billing, templates (all deprecated) |
| **Redis** | ❌ Deprecated | Rate limiting, sessions (middleware deprecated) |

**Reason**: The custom core runtime uses in-process asyncio queues, not external services.

**Current Architecture**:
```
Dashboard → API → Core Runtime (asyncio)
```

**Future**: Re-enable services when platform features are restored.

## Database Status

**Current**: Database is optional. API works without it.

**Reason**: The deprecated features needed PostgreSQL, but the core doesn't.

**Future**: Re-enable database when you re-activate platform features.

## Migration Impact

**No breaking changes**. The core system is unchanged.

- ✅ Core orchestration works the same
- ✅ API endpoints are the same
- ✅ Dashboard works the same
- ❌ Platform features are disabled (but code is preserved)

## Summary

**What we did**: Archived unnecessary complexity
**Why**: Core works without it
**When to bring back**: When you have users and revenue to justify it

**The code still exists** in `platform-deprecated/` - it's not deleted, just not active.

---

**Decision**: jrnew on 2026-02-07
**Rationale**: "Build working core first, add enterprise features later"
