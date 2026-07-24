"""
Template Service

Business logic for agent template management.
"""

from json import loads as json_loads
from uuid import uuid4
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from templates.models import Template


# Built-in templates (seeded on startup)
BUILTIN_TEMPLATES = [
    {
        "id": "hello-world",
        "name": "hello-world",
        "display_name": "Hello World",
        "description": "A simple agent that says hello. Great for testing.",
        "category": "basic",
        "tags": "simple,testing",
        "config": {
            "topology": "single",
            "agents": [
                {
                    "name": "greeter",
                    "role": "You are a friendly assistant that greets people.",
                    "model": "claude-sonnet-4-5",
                    "tools": [],
                }
            ],
            "consensus": "none",
        },
    },
    {
        "id": "researcher",
        "name": "researcher",
        "display_name": "Research Agent",
        "description": "An agent that can search the web and compile research on any topic.",
        "category": "research",
        "tags": "web-search,research,analysis",
        "config": {
            "topology": "hierarchical",
            "agents": [
                {
                    "name": "coordinator",
                    "role": "You coordinate research tasks and compile findings.",
                    "model": "claude-sonnet-4-5",
                },
                {
                    "name": "searcher",
                    "role": "You search the web for information on specific topics.",
                    "model": "claude-haiku-4-5",
                    "tools": ["web_search", "web_reader"],
                },
                {
                    "name": "analyst",
                    "role": "You analyze research findings and extract key insights.",
                    "model": "claude-sonnet-4-5",
                },
            ],
            "consensus": "majority",
        },
    },
    {
        "id": "analyst",
        "name": "analyst",
        "display_name": "Data Analyst",
        "description": "An agent that can analyze data, create charts, and generate reports.",
        "category": "analysis",
        "tags": "data,charts,reports",
        "config": {
            "topology": "mesh",
            "agents": [
                {
                    "name": "data_processor",
                    "role": "You process and clean data for analysis.",
                    "model": "claude-haiku-4-5",
                    "tools": ["file_reader", "data_parser"],
                },
                {
                    "name": "analyst",
                    "role": "You analyze data and identify patterns.",
                    "model": "claude-sonnet-4-5",
                },
                {
                    "name": "visualizer",
                    "role": "You create charts and visualizations from data.",
                    "model": "claude-sonnet-4-5",
                    "tools": ["chart_generator"],
                },
            ],
            "consensus": "unanimous",
        },
    },
    {
        "id": "monitor",
        "name": "monitor",
        "display_name": "System Monitor",
        "description": "An agent that monitors system health and sends alerts.",
        "category": "monitoring",
        "tags": "monitoring,alerts,devops",
        "config": {
            "topology": "star",
            "agents": [
                {
                    "name": "coordinator",
                    "role": "You coordinate monitoring tasks and send alerts.",
                    "model": "claude-sonnet-4-5",
                },
                {
                    "name": "metrics_collector",
                    "role": "You collect system metrics and logs.",
                    "model": "claude-haiku-4-5",
                    "tools": ["metrics_collector", "log_reader"],
                },
                {
                    "name": "health_checker",
                    "role": "You check health of services and endpoints.",
                    "model": "claude-haiku-4-5",
                    "tools": ["http_health_check", "port_checker"],
                },
            ],
            "consensus": "weighted",
        },
    },
]


class TemplateService:
    """Service for managing agent templates."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_template(self, template_id: str) -> Optional[Template]:
        """Get template by ID."""
        result = await self.db.execute(
            select(Template).where(Template.id == template_id)
        )
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        category: str | None = None,
        is_public: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Template]:
        """List templates with optional filters."""
        query = select(Template).where(Template.is_public == is_public)

        if category:
            query = query.where(Template.category == category)

        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_template(
        self,
        name: str,
        display_name: str,
        description: str,
        config: dict,
        category: str = "general",
        tags: list[str] | None = None,
        is_public: bool = True,
    ) -> Template:
        """Create a new template."""
        import json

        template = Template(
            id=str(uuid4()),
            name=name,
            display_name=display_name,
            description=description,
            config=json.dumps(config),
            category=category,
            tags=",".join(tags or []),
            is_public=is_public,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        return template

    async def seed_templates(self) -> None:
        """Seed built-in templates if they don't exist."""
        import json

        for tmpl_data in BUILTIN_TEMPLATES:
            # Check if template exists
            existing = await self.get_template(tmpl_data["id"])

            if not existing:
                template = Template(
                    id=tmpl_data["id"],
                    name=tmpl_data["name"],
                    display_name=tmpl_data["display_name"],
                    description=tmpl_data["description"],
                    config=json.dumps(tmpl_data["config"]),
                    category=tmpl_data["category"],
                    tags=tmpl_data["tags"],
                    is_public=True,
                )
                self.db.add(template)

        await self.db.commit()
