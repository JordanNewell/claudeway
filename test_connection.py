"""
Test script to verify the platform is connected to the core orchestration engine.
"""

import asyncio
import os

from api.state import get_runtime
from api.orchestration import OrchestrationService


async def test_connection():
    """Test that the platform can talk to the core engine."""
    print("=" * 60)
    print("Claudeway - Platform to Core Connection Test")
    print("=" * 60)

    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Warning: ANTHROPIC_API_KEY not set - agents will not be able to make API calls")
        print("But we can still test the connection...")

    # Test 1: Runtime initialization
    print("\n[1/4] Testing Runtime initialization...")
    runtime = get_runtime()
    await runtime.start()
    print("[OK] Runtime initialized")

    # Test 2: Create orchestration service
    print("\n[2/4] Creating OrchestrationService...")
    service = OrchestrationService()
    print("[OK] OrchestrationService created")

    # Test 3: Create a test swarm
    print("\n[3/4] Creating test swarm...")
    swarm = await service.create_swarm(
        name="TestSwarm",
        description="A test swarm for connection verification",
        agents=[
            {
                "name": "TestAgent",
                "role": "Test Specialist",
                "instructions": "You are a test agent.",
            }
        ],
    )
    print(f"[OK] Swarm created: {swarm['id']}")
    print(f"  Name: {swarm['name']}")
    print(f"  Agent count: {swarm['agent_count']}")

    # Test 4: List agents
    print("\n[4/4] Listing agents...")
    agents = await service.list_agents()
    print(f"[OK] Found {len(agents)} agents")

    # Show runtime status
    print("\n" + "=" * 60)
    print("RUNTIME STATUS:")
    print("=" * 60)
    status = service.get_runtime_status()
    print(f"Running: {status['running']}")
    print(f"Agent count: {status['agent_count']}")
    print(f"Swarm count: {status['swarm_count']}")

    # Cleanup
    await runtime.stop()
    print("\n[OK] All tests passed! Platform is connected to core.")

    return True


if __name__ == "__main__":
    asyncio.run(test_connection())
