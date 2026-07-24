"""
Agent API Router

REST API endpoints for agent deployment and management.
Connected to the Claudeway core orchestration engine.
"""

# from typing import list (builtin in Python 3.9+)
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status

from api.orchestration import OrchestrationService
from api.state import get_runtime


class DeployAgentRequest(BaseModel):
    """Request to deploy a new agent/swarm."""
    name: str
    description: str
    agents: list[dict]  # List of agent configs with name, role, instructions
    template_id: str | None = None
    config: dict = {}


class SendMessageRequest(BaseModel):
    """Request to send a task to a swarm."""
    task_description: str
    task_data: dict = {}
    user_id: str | None = None


class CreateCoordinatorRequest(BaseModel):
    """Request to create a coordinator with specialists."""
    name: str
    specialists: list[dict]  # List of specialist configs


router = APIRouter()


async def get_orchestration_service() -> OrchestrationService:
    """Get orchestration service instance."""
    return OrchestrationService()


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def deploy_agent(
    request: DeployAgentRequest,
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> dict:
    """Deploy a new agent swarm."""
    try:
        swarm = await orchestration_service.create_swarm(
            name=request.name,
            description=request.description,
            agents=request.agents,
        )
        return swarm
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deploy agent: {str(e)}",
        )


@router.get("/", response_model=list[dict])
async def list_agents(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> list[dict]:
    """List all agents across all swarms."""
    try:
        agents = await orchestration_service.list_agents(
            status=status,
            limit=limit,
            offset=offset,
        )
        return agents
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}",
        )


@router.post("/{swarm_id}/task", response_model=dict)
async def submit_task(
    swarm_id: str,
    request: SendMessageRequest,
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> dict:
    """Submit a task to a swarm for processing."""
    try:
        result = await orchestration_service.process_task(
            swarm_id=swarm_id,
            task_description=request.task_description,
            task_data=request.task_data,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process task: {str(e)}",
        )


@router.post("/coordinator", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_coordinator(
    request: CreateCoordinatorRequest,
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> dict:
    """Create a coordinator with specialist agents."""
    try:
        coordinator = await orchestration_service.create_coordinator(
            name=request.name,
            specialists=request.specialists,
        )
        return coordinator
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create coordinator: {str(e)}",
        )


@router.get("/status", response_model=dict)
async def get_status(
    orchestration_service: OrchestrationService = Depends(get_orchestration_service),
) -> dict:
    """Get the current runtime status."""
    return orchestration_service.get_runtime_status()
