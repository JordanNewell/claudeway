# Claudeway Naming Guide

## The Two "Agent" Concepts

Claudeway has two different concepts that were confusingly both called "agent":

### 1. Core Agent (`core/agent.py`) - The Intelligence

**What it is:** The actual Claude-powered AI agent that thinks and responds.

```python
from core.agent import Agent, AgentConfig

agent = Agent(
    config=AgentConfig(
        name="Researcher",
        role="Analyst",
        instructions="You analyze problems thoroughly."
    )
)

response = await agent.think("What is async programming?")
```

**Purpose:**
- Calls Anthropic API
- Maintains conversation memory
- Does the actual thinking/reasoning

**Location:** `core/agent.py`

### 2. SwarmDeployment (`api/agents/deployment.py`) - The Database Record

**What it is:** A database row tracking a deployed swarm in the platform.

```python
from agents.deployment import SwarmDeployment

deployment = SwarmDeployment(
    id="uuid-123",
    tenant_id="tenant-abc",
    name="research-swarm",
    swarm_id="research-swarm-123",  # References core Swarm
    status="running"
)
```

**Purpose:**
- Tracks deployment metadata
- Links to tenant for billing
- Stores configuration
- Enables multi-tenancy

**Location:** `api/agents/deployment.py`

## Quick Reference

| | Core Agent | SwarmDeployment |
|---|---|---|
| **File** | `core/agent.py` | `api/agents/deployment.py` |
| **What** | Claude intelligence | Database record |
| **Does** | Thinks, responds | Tracks deployment |
| **Stored in** | Memory (Runtime) | PostgreSQL |
| **Analogy** | The brain | The employee record |

## Import Guide

```python
# Core intelligence (actual agents)
from core.agent import Agent, AgentConfig
from core.swarm import Swarm, SwarmConfig
from core.coordinator import Coordinator, CoordinatorConfig

# Platform tracking (database records)
from agents.deployment import SwarmDeployment, DeploymentStatus

# Backwards compatible (deprecated)
from agents.deployment import Agent, AgentStatus  # Aliases for SwarmDeployment
```

## Why This Distinction Matters

When you call "Deploy Agent" in the dashboard:

1. **Platform Layer** creates a `SwarmDeployment` record (database)
2. **OrchestrationService** creates a `Swarm` with `Agent` objects (memory)
3. **Core Agents** do the actual thinking via Claude API

```
User clicks "Deploy"
    ↓
API: SwarmDeployment{name: "research-swarm"} → Database
    ↓
OrchestrationService: Swarm{agents: [Agent, Agent, Agent]} → Memory
    ↓
Core Agent: await agent.think() → Anthropic API → Response
```

## Migration Notes

**Old code:**
```python
from agents.models import Agent  # Was confusing!
```

**New code:**
```python
# For actual AI agents
from core.agent import Agent

# For database records
from agents.deployment import SwarmDeployment
```

**Table name:** Changed from `agents` to `swarm_deployments`
- In production, run a migration to rename the table
- Old data remains compatible via backwards compatibility aliases
