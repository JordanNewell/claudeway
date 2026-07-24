# ⚠️ Platform Features - DEPRECATED

**Status**: NOT ACTIVE - Moved here on 2026-02-07

## What's Deprecated

These features were built **before** proving the core orchestration engine worked.
This was the "Curtis anti-pattern" - building enterprise features without a working product.

- **billing/** - Invoicing, Stripe payments, revenue tracking
- **tenants/** - Multi-tenant SaaS features, tier management
- **templates/** - Agent template marketplace
- **analytics/** - Usage analytics and reporting
- **gateway/** - Old Claude-Flow client (dead code)

## Why It's Deprecated

### Use Case NOW: ❌
- **0 users** - No one to bill
- **0 revenue** - Nothing to track
- **0 customers** - No need for multi-tenancy
- **Working core** - The orchestration engine works WITHOUT any of this

### Production Headache NOW: 🔴
- **Database dependency** - PostgreSQL must run or API fails
- **Complexity** - 5+ services to do one thing (deploy an agent)
- **Migrations** - Schema changes to manage
- **Failure modes** - More moving parts that can break

## When To Re-Activate

**Re-activate WHEN:**
1. You have 100+ active users
2. Someone is actually willing to pay
3. The complexity is justified by revenue

**How to re-activate:**
1. Move folders back from `platform-deprecated/` to `api/`
2. Uncomment imports in `api/main.py`
3. Uncomment middleware in `api/main.py`
4. Run database migrations

## The "Curtis Lesson"

> "Build working core first, add enterprise features later."

**What we did wrong:**
1. Built billing → Had no customers
2. Built multi-tenancy → Had only 1 user (ourselves)
3. Built templates → No marketplace
4. Built ALL of this → Before the core even worked

**What we should have done:**
1. Prove core works ✅ (done 2026-02-07)
2. Get users
3. Add features as needed
4. Keep it simple

## Current Working System

The platform works great WITHOUT any of this:

- **Core orchestration** ✅ (core/)
- **Agent deployment** ✅ (api/agents/)
- **Dashboard** ✅ (dashboard/)
- **API endpoints** ✅ (/v1/agents/*)

That's all you need for a working multi-agent system.

---

**Archived by**: jrnew on 2026-02-07
**Reason**: Focus on working core, remove unnecessary complexity
