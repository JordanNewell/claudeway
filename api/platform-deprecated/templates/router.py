"""
Template API Router

REST API endpoints for agent template management.
"""

# from typing import list (builtin in Python 3.9+)
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from templates.service import TemplateService


class CreateTemplateRequest(BaseModel):
    """Request to create a new template."""
    name: str
    display_name: str
    description: str
    config: dict
    category: str = "general"
    tags: list[str] = []
    is_public: bool = True


router = APIRouter()


@router.get("/", response_model=list[dict])
async def list_templates(
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all public templates."""
    service = TemplateService(db)
    templates = await service.list_templates(
        category=category,
        is_public=True,
        limit=limit,
        offset=offset,
    )
    return [t.to_dict() for t in templates]


@router.get("/{template_id}", response_model=dict)
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get template by ID."""
    service = TemplateService(db)
    template = await service.get_template(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        )

    return template.to_dict()


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: CreateTemplateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new template."""
    service = TemplateService(db)

    try:
        template = await service.create_template(
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            config=request.config,
            category=request.category,
            tags=request.tags,
            is_public=request.is_public,
        )
        return template.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
