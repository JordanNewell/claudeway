# Claudeway - Architecture Documentation

Technical architecture of the Claudeway multi-agent orchestration platform.

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [Platform Layer](#platform-layer)
5. [Data Models](#data-models)
6. [API Design](#api-design)
7. [Frontend Architecture](#frontend-architecture)
8. [Deployment](#deployment)
9. [Security](#security)
10. [Relationship to Claude](#relationship-to-claude)

---

## Overview

Claudeway is a **multi-agent orchestration platform** with both a working core engine and a monetizable platform layer. It enables Claude agents to work together collaboratively through various coordination patterns.

### Key Design Principles

- **Working core first** - Orchestration engine that actually works
- **Multi-tenancy ready** - Complete tenant isolation
- **API-first** - Everything accessible via REST
- **Observable** - Built-in metrics and status endpoints
- **Monetizable** - Usage tracking and billing

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Client Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   Web UI     │  │   CLI SDK    │  │   API CLI    │             │
│  │ (Next.js)    │  │  (Python)    │  │   (curl)     │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ HTTPS
┌─────────────────────────────▼───────────────────────────────────────┐
│                       API Gateway Layer                             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  FastAPI + Middleware                                        │  │
│  │  • Tenant Context (X-Tenant-ID)                              │  │
│  │  • Rate Limiting (Redis)                                     │  │
│  │  • Auth/JWT (future)                                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
┌────────▼─────────┐  ┌──────▼──────┐  ┌────────▼────────┐
│  Tenant Service  │  │ Orchestrator │  │ Billing Svc    │
│  • CRUD          │  │ • Swarms     │  │ • Usage Track  │
│  • Tier Mgmt     │  │ • Agents     │  │ • Invoices     │
└────────┬─────────┘  └──────┬──────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                    Core Orchestration Engine                         │
│  ┌─────────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐   │
│  │   Runtime   │  │  Swarm  │  │Agent    │  │  Coordinator    │   │
│  │  (process)  │  │ (p2p)   │  │(Claude) │  │  (hierarchical) │   │
│  └─────────────┘  └─────────┘  └─────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                      Data Layer                                     │
│  ┌─────────────┐  ┌─────────┐                                       │
│  │ PostgreSQL  │  │ Redis   │                                       │
│  │ (metadata)  │  │ (cache) │                                       │
│  └─────────────┘  └─────────┘                                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                    External Services                                │
│  ┌──────────────┐  ┌──────────────┐                                │
│  │  Anthropic   │  │   Stripe     │                                │
│  │     API      │  │  Payments    │                                │
│  └──────────────┘  └──────────────┘                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### Agent (`core/agent.py`)

The fundamental unit - a single Claude agent.

```python
class Agent:
    def __init__(self, config: AgentConfig, api_key: str):
        self.config = config
        self.client = Anthropic(api_key=api_key)
        self.messages = []

    async def think(self, input_message: str) -> str:
        # Call Anthropic API
        response = self.client.messages.create(...)
        return response.content[0].text
```

**Capabilities**:
- Conversation memory
- Configurable model, temperature, max_tokens
- System prompt from role + instructions

### Swarm (`core/swarm.py`)

Multi-agent peer-to-peer coordination.

```python
class Swarm:
    def __init__(self, config: SwarmConfig):
        self.agents = {name: Agent(cfg) for name, cfg in config.agents}
        self.config = config

    async def process(self, task: Task) -> Task:
        # All agents work on the same task
        responses = await self._collect_agent_responses(task)
        # Run consensus to combine results
        final_result = await self._run_consensus(responses)
        return final_result
```

**Capabilities**:
- Parallel agent execution
- Consensus mechanism
- Task history tracking

### Coordinator (`core/coordinator.py`)

Hierarchical task decomposition pattern.

```python
class Coordinator:
    def __init__(self, config: CoordinatorConfig):
        self.agent = Agent(config)  # Manager agent
        self.sub_agents = {}

    def add_sub_agent(self, name: str, agent: Agent):
        self.sub_agents[name] = agent

    async def coordinate(self, task: Task) -> Task:
        # Decompose task into sub-tasks
        sub_tasks = await self._decompose_task(task)
        # Assign to specialists
        await self._assign_sub_tasks(sub_tasks)
        # Execute and synthesize
        results = await self._execute_sub_tasks(sub_tasks)
        final_result = await self._synthesize_results(task, results)
        return final_result
```

**Capabilities**:
- Task decomposition
- Specialist assignment
- Result synthesis

### Runtime (`core/runtime.py`)

Process supervision and lifecycle management.

```python
class Runtime:
    def __init__(self):
        self.agents = {}  # agent_id -> AgentProcess
        self.swarms = {}  # swarm_id -> Swarm

    def spawn_agent(self, config: AgentConfig) -> str:
        agent = Agent(config)
        agent_process = AgentProcess(id=agent_id, agent=agent)
        self.agents[agent_id] = agent_process
        asyncio.create_task(agent_process.start())
        return agent_id

    def create_swarm(self, config: SwarmConfig) -> str:
        swarm = Swarm(config)
        self.swarms[swarm_id] = swarm
        return swarm_id

    async def submit_task(self, swarm_id: str, task: Task) -> Task:
        swarm = self.swarms[swarm_id]
        return await swarm.process(task)
```

**Capabilities**:
- Agent process supervision
- Health monitoring
- Task routing
- Lifecycle management

---

## Platform Layer

### API Gateway (`api/main.py`)

FastAPI application with middleware:
- CORS handling
- Tenant context extraction
- Rate limiting (future)
- Health checks

### Orchestration Service (`api/orchestration.py`)

Bridge between API and core engine:

```python
class OrchestrationService:
    def __init__(self):
        self.runtime = get_runtime()

    async def create_swarm(self, name, description, agents):
        # Convert API dict to AgentConfig objects
        agent_configs = [AgentConfig(**a) for a in agents]
        swarm_config = SwarmConfig(name=name, agents=agent_configs)
        swarm_id = self.runtime.create_swarm(swarm_config)
        return {"id": swarm_id, "name": name, "status": "running"}

    async def process_task(self, swarm_id, task_description, task_data):
        task = Task(id=uuid4(), description=task_description, input_data=task_data)
        completed_task = await self.runtime.submit_task(swarm_id, task)
        return {"task_id": task.id, "result": completed_task.result}
```

### Services

| Service | Location | Responsibility |
|---------|----------|---------------|
| **OrchestrationService** | `orchestration.py` | Bridge to core engine |
| **TenantService** | `tenants/service.py` | Multi-tenant CRUD, tier management |
| **TemplateService** | `templates/service.py` | Agent template management |
| **BillingService** | `billing/service.py` | Usage tracking, invoicing |

---

## Data Models

### Tenant

```python
class Tenant:
    id: str
    name: str
    email: str
    tier: "free" | "pro" | "enterprise"
    status: "active" | "suspended" | "cancelled"
    max_agents: int
    max_messages_per_month: int
    stripe_customer_id?: str
    stripe_subscription_id?: str
```

### Agent (Database)

```python
class Agent:
    id: str
    tenant_id: str
    name: str
    template_id: str
    status: "deploying" | "running" | "stopped" | "error"
    swarm_id?: str  # Runtime swarm ID
    config: str     # JSON config
    created_at: datetime
    last_active_at?: datetime
```

### Swarm (Runtime)

```python
class Swarm:
    config: SwarmConfig
    agents: dict[str, Agent]
    task_history: list[Task]
    topology: str  # "hierarchical_mesh", "peer_to_peer", etc.
    consensus_method: str
```

### Template

```python
class Template:
    id: str
    name: str
    display_name: str
    description: str
    category: str
    tags: list[str]
    config: str  # JSON with agents, topology, etc.
```

---

## API Design

### Endpoints

```
# Agent Swarms
POST   /v1/agents                     # Deploy swarm
GET    /v1/agents                     # List all agents
POST   /v1/agents/:id/task            # Submit task to swarm
GET    /v1/agents/status              # Runtime status
POST   /v1/agents/coordinator         # Create coordinator

# Tenant Management
POST   /v1/tenants                    # Create tenant
GET    /v1/tenants                    # List tenants
GET    /v1/tenants/:id                # Get tenant
PUT    /v1/tenants/:id/tier           # Update tier

# Billing & Usage
GET    /v1/billing/usage              # Get usage stats
GET    /v1/billing/invoices           # List invoices
POST   /v1/billing/invoices/generate  # Generate invoice

# Templates
GET    /v1/templates                  # List templates
GET    /v1/templates/:id              # Get template details
POST   /v1/templates                  # Create template (admin)
```

### Request/Response Examples

**Deploy Swarm**:
```json
POST /v1/agents
{
  "name": "research-swarm",
  "description": "A swarm for research tasks",
  "agents": [
    {"name": "Researcher", "role": "Analyst", "instructions": "..."},
    {"name": "Critic", "role": "Reviewer", "instructions": "..."},
    {"name": "Synthesizer", "role": "Integrator", "instructions": "..."}
  ]
}

Response:
{
  "id": "research-swarm-1234567890.123",
  "name": "research-swarm",
  "agent_count": 3,
  "status": "running"
}
```

**Submit Task**:
```json
POST /v1/agents/{swarm_id}/task
{
  "task_description": "What are the benefits of async programming?",
  "task_data": {"domain": "software engineering"}
}

Response:
{
  "task_id": "task-uuid",
  "swarm_id": "research-swarm-...",
  "status": "completed",
  "result": {
    "final_answer": "Async programming enables...",
    "all_responses": {...}
  }
}
```

---

## Frontend Architecture

### Tech Stack

- **Next.js 15** - App Router, React 19
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **shadcn/ui** - Component library
- **React Query** - Data fetching
- **Zustand** - State management
- **Axios** - HTTP client

### Pages

| Page | Route | Description |
|------|-------|-------------|
| **Home** | `/` | Landing page |
| **Dashboard** | `/dashboard` | Overview with stats |
| **Agents** | `/dashboard/agents` | Swarm management |
| **Tenants** | `/dashboard/tenants` | Tenant management |
| **Billing** | `/dashboard/billing` | Usage & invoices |
| **Settings** | `/dashboard/settings` | User settings |

### Key Components

- **DeployAgentModal** - Swarm deployment UI with template selection
- **Sidebar** - Navigation
- **Agent Cards** - Display swarm status with task submission

---

## Deployment

### Development

```bash
# Install dependencies
py -m pip install -e .
cd dashboard && npm install

# Start API
cd api && py main.py

# Start Dashboard
cd dashboard && npm run dev
```

### Production

```bash
# Frontend: Build static files
npm run build

# Backend: Use gunicorn
gunicorn claudeway.api.main:app -w 4 -k uvicorn.workers.UvicornWorker

# Infrastructure: Use managed services
# - Cloud SQL (PostgreSQL)
# - ElastiCache (Redis)
# - Load balancer
```

---

## Security

### Multi-Tenancy

- **Tenant isolation** via `tenant_id` on all resources
- **Row-level security** in queries
- **Rate limiting** per tenant (future)
- **Usage quotas** per tier

### Authentication (Future)

- JWT tokens via `python-jose`
- Refresh token rotation
- OIDC integration planned

### Authorization

- **Tier-based limits** enforced at service layer
- **Resource ownership** verified before operations
- **Rate limiting** via Redis sliding window

### Secrets

- Environment variables for all secrets
- `.env` file (gitignored)
- **Never commit** API keys or tokens

---

## Relationship to Claude

**Important**: Claudeway does NOT replace or govern Claude.

### The Relationship

```
┌─────────────────────────────────────────────────────┐
│                  Claudeway                          │
│  • Coordinates multiple agents                      │
│  • Manages agent lifecycles                         │
│  • Routes tasks to appropriate agents               │
│  • Combines agent perspectives                      │
└─────────────────────────────────────────────────────┘
                         ↓
                         uses
                         ↓
┌─────────────────────────────────────────────────────┐
│                   Claude (Anthropic API)            │
│  • Intelligence, reasoning, creativity              │
│  • Tool use capabilities                            │
│  • Context and memory management                    │
└─────────────────────────────────────────────────────┘
```

### Analogy

- **Claude** = The brain (intelligence)
- **Claudeway** = The organization system (coordination)

Each agent in Claudeway:
1. Uses Claude as its "brain" via Anthropic API
2. Participates in multi-agent collaboration patterns
3. Is supervised by the Runtime for health and lifecycle

### What Claudeway Provides

- **Multi-agent coordination** - How agents talk to each other
- **Process supervision** - Keeping agents alive and healthy
- **Task routing** - Getting work to the right agents
- **Consensus mechanisms** - Combining multiple agent perspectives

### What Claude Provides

- **Intelligence** - Reasoning, analysis, creativity
- **Tool use** - Ability to call external functions
- **Memory** - Conversation and context management
- **Safety** - Built-in safety guidelines

---

## Orchestration Patterns

### Pattern 1: Peer-to-Peer Swarm

```
Task → [Agent1] ─┐
      [Agent2] ─┼→ Consensus → Result
      [Agent3] ─┘
```

**Best for**:
- Diverse perspectives on same problem
- Research and analysis
- Brainstorming and ideation

### Pattern 2: Hierarchical Coordinator

```
Task → Coordinator → [Sub-task1 → Specialist1]
                   → [Sub-task2 → Specialist2]
                   → [Sub-task3 → Specialist3]
       → Synthesis → Result
```

**Best for**:
- Complex multi-step tasks
- Parallel specialized work
- Structured workflows

### Pattern 3: Pipeline

```
Task → Agent1 → Output1 → Agent2 → Output2 → Agent3 → Result
```

**Best for**:
- Sequential processing
- Multi-stage workflows
- Assembly-line style tasks

---

**Last Updated**: 2026-02-07
