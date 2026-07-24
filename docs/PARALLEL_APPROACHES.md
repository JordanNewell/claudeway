# Parallel Processing in Claude - Two Approaches

## The Confusion

Claude has **two different ways** to run parallel agents. They serve different purposes.

## Quick Comparison

| Aspect | Native Parallel (SDK) | Claudeway Tool |
|--------|----------------------|----------------|
| **Persistence** | Temporary (dies after response) | Persistent (runs until stopped) |
| **Reusability** | One-shot | Reusable across tasks |
| **Management** | Automatic | Manual (start/stop/monitor) |
| **Memory** | Conversation-scoped | Swarm-scoped |
| **Use Case** | Quick parallel tasks | Dedicated specialist teams |
| **Overhead** | Low | Higher |

## When to Use Which

### Use Native Parallel (SDK) when:

```python
# Claude's built-in capability - no tool needed
"Analyze these 3 documents in parallel and summarize"
```

✅ **Quick concurrent operations**
✅ **One-shot parallel processing**
✅ **Results needed immediately**
✅ **No need for specialist persistence**

### Use Claudeway Tool when:

```python
# Creates a persistent, reusable team
claudeway(
    action="deploy_swarm",
    swarm_name="research-team",
    agents=[...]
)
```

✅ **Need persistent specialist teams**
✅ **Agents maintain state across tasks**
✅ **Want to manage swarm lifecycle**
✅ **Reusing the same team multiple times**

## Example Scenarios

### Scenario 1: Quick Document Analysis
**Wrong:** Deploy a swarm just to analyze 3 documents once
**Right:** Use native parallel processing

```
Claude: "I'll analyze these 3 documents in parallel using my native capability"
```

### Scenario 2: Research Team
**Wrong:** Spin up new agents for each research query
**Right:** Deploy a persistent research swarm

```
Claude: "This project needs ongoing research. I'll deploy a dedicated research swarm
that I can query multiple times."
<uses claudeway tool>
```

## Decision Tree

```
Need parallel processing?
         ↓
    Will you reuse these agents?
         ↓
    Yes → Use Claudeway tool
         ↓
    No → Use native parallel
```

## Claude's Internal Logic

When Claude has both capabilities, it should think:

```
1. Is this a one-shot parallel task?
   YES → Use native parallel (faster, simpler)

2. Will I need these specialists again?
   YES → Deploy a swarm (persistent, reusable)

3. Do I need to manage/monitor the agents?
   YES → Use Claudeway tool (has status, management)

4. Is this simple concurrency?
   YES → Use native parallel (built-in)
```

## Code Comparison

### Native Parallel (what Claude does automatically)

```python
# This happens automatically - Claude doesn't need to think about it
async def process_three_things():
    results = await asyncio.gather(
        analyze(doc1),
        analyze(doc2),
        analyze(doc3)
    )
```

### Claudeway Tool (explicit decision)

```python
# Claude must CHOOSE to use this
claudeway(
    action="deploy_swarm",
    swarm_name="my-team",
    agents=[...]
)
# Later...
claudeway(
    action="submit_task",
    swarm_id="my-team-123",
    task="Do another task"
)
```

## Key Takeaway

**Native parallel** = "I need to do 3 things at once, right now"
**Claudeway tool** = "I need a dedicated team that will work on multiple tasks over time"

The tool description now explicitly states this distinction so Claude knows when to use which approach.
