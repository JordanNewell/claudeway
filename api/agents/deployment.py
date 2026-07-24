"""
Swarm Deployment Models

Data models for tracking deployed swarms in the platform layer.
Note: These are database records, NOT the actual agents (which are in core/agent.py).
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class DeploymentStatus(str, Enum):
    """Swarm deployment status."""
    DEPLOYING = "deploying"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class SwarmDeployment(Base):
    """Swarm deployment model - tracks a deployed swarm in the platform.

    This is a DATABASE RECORD that tracks deployment metadata.
    The actual agents that do the thinking are in core/agent.py.
    """

    __tablename__ = "swarm_deployments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # NOTE: tenant_id deprecated with multi-tenancy feature
    # Kept for backwards compatibility, removed FK constraint
    tenant_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Configuration
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=True)
    template_id: Mapped[str | None] = mapped_column(String, nullable=True)
    config: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string

    # Runtime integration
    swarm_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)  # References core Swarm

    # Status
    status: Mapped[str] = mapped_column(String, default=DeploymentStatus.DEPLOYING, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    # Metadata
    agent_count: Mapped[int] = mapped_column(Integer, default=0)  # Number of agents in the swarm

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "template_id": self.template_id,
            "status": self.status,
            "error_message": self.error_message,
            "swarm_id": self.swarm_id,
            "agent_count": self.agent_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
        }


# Backwards compatibility aliases
Agent = SwarmDeployment  # Old name, deprecated
AgentStatus = DeploymentStatus  # Old name, deprecated
