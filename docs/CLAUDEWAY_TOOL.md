# Claudeway Tool - Meta-Cognitive Swarm Management

## Overview

The Claudeway tool enables Claude agents to deploy and manage their own swarms of sub-agents. This creates a **meta-cognitive** system where Claude can:

1. **Recognize** when a task needs multiple specialized perspectives
2. **Deploy** a swarm of specialized agents automatically
3. **Coordinate** the sub-agents to work on the task
4. **Synthesize** results from multiple agents

## How It Works

```
User sends task to Claude (with Claudeway tool)
         ↓
Claude analyzes the task
         ↓
Claude recognizes: "This needs multiple specialists"
         ↓
Claude uses claudeway tool:
  - deploy_swarm with specialized agents
         ↓
Claudeway spawns sub-agents (also Claude instances)
         ↓
Sub-agents work in parallel
         ↓
Claude receives results and synthesizes
```

## Example Usage

```python
from core.agent import Agent, AgentConfig
from core.tools.claudeway import create_claudeway_tool
from core.runtime import Runtime

# Create runtime
runtime = Runtime()
await runtime.start()

# Create an orchestrator agent WITH the Claudeway tool
orchestrator_config = AgentConfig(
    name="Orchestrator",
    role="A meta-cognitive agent that coordinates specialized swarms",
    instructions="""You are a swarm manager. When you receive complex tasks,
    analyze them and deploy specialized sub-agents using the claudeway tool.
    Each sub-agent should have a specific role and expertise.""",
    tools=[create_claudeway_tool(runtime)]
)

orchestrator = Agent(orchestrator_config)

# Now the orchestrator can deploy its own swarms!
response = await orchestrator.think(
    "Research the latest AI trends and create a comprehensive report. "
    "This will require research, analysis, and writing expertise."
)

# Claude will automatically:
# 1. Recognize the task needs multiple specialists
# 2. Deploy a swarm with researcher, analyst, and writer agents
# 3. Submit the task to the swarm
# 4. Synthesize the results
```

## Tool Schema

```json
{
  "name": "claudeway",
  "description": "Deploy and manage Claude agent swarms...",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["deploy_swarm", "submit_task", "get_status", "list_swarms"]
      },
      "swarm_name": {"type": "string"},
      "agents": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "role": {"type": "string"},
            "instructions": {"type": "string"}
          }
        }
      },
      "swarm_id": {"type": "string"},
      "task": {"type": "string"}
    }
  }
}
```

## Actions

### deploy_swarm
Create a new swarm with specialized agents.

```python
claudeway(
    action="deploy_swarm",
    swarm_name="research-team",
    agents=[
        {
            "name": "researcher",
            "role": "Finds and gathers information",
            "instructions": "Search for reliable sources, extract key facts"
        },
        {
            "name": "analyst",
            "role": "Analyzes data and finds patterns",
            "instructions": "Identify trends, synthesize findings"
        }
    ]
)
```

### submit_task
Send a task to an existing swarm.

```python
claudeway(
    action="submit_task",
    swarm_id="research-team-123",
    task="Research quantum computing advances in 2024"
)
```

### get_status
Check the status of a swarm.

```python
claudeway(
    action="get_status",
    swarm_id="research-team-123"
)
```

### list_swarms
List all active swarms.

```python
claudeway(action="list_swarms")
```

## Claude's Decision Process

When Claude has the Claudeway tool, it can:

1. **Analyze task complexity**
   - "This is too complex for one agent"
   - "Different aspects require different expertise"

2. **Design swarm architecture**
   - "I need a researcher, analyst, and writer"
   - "These roles should work in parallel"

3. **Deploy automatically**
   - Use `deploy_swarm` with appropriate roles
   - Define clear instructions for each agent

4. **Coordinate execution**
   - Use `submit_task` to send work
   - Use `get_status` to monitor progress

5. **Synthesize results**
   - Combine outputs from all sub-agents
   - Create cohesive final response

## Benefits

| Without Claudeway Tool | With Claudeway Tool |
|------------------------|---------------------|
| Claude thinks alone | Claude spawns specialists |
| Sequential tool use | Parallel agent execution |
| One perspective | Multiple specialized perspectives |
| Manual swarm deployment | Automatic swarm deployment |
| You coordinate | Claude coordinates |

## Example Conversation

```
User: "Write a comprehensive analysis of climate change economics."

Claude (without tool): [Writes analysis alone]

Claude (with Claudeway tool):
  "This complex task requires multiple perspectives.
   I'll deploy a specialized swarm:
   - Economist: Economic impact analysis
   - Scientist: Climate data review
   - Policy analyst: Policy implications

   <uses claudeway tool to deploy swarm>
   <submits task to swarm>
   <synthesizes their findings>"
```

## Implementation Notes

- The tool requires a Runtime instance to manage swarms
- Each spawned agent is a full Claude instance with its own API calls
- The orchestrator agent maintains conversation context
- Tool results include swarm IDs for follow-up actions
- Errors are caught and returned in tool results

## Future Enhancements

- Swarm templates (pre-defined agent teams)
- Hierarchical swarms (swarms deploying swarms)
- Persistent swarms (long-running specialist teams)
- Swarm memory (shared context across agents)
- Swarm optimization (learn which patterns work best)
