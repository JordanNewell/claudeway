"""
Template Models

Pre-built agent template configurations.
"""

from datetime import datetime
# from typing import dict  # dict is built-in in Python 3.9+

from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Template(Base):
    """Agent template model."""

    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)

    # Configuration (JSON string)
    # Contains: topology, consensus, agents, tools, etc.
    config: Mapped[str] = mapped_column(Text, nullable=False)

    # Template metadata
    category: Mapped[str] = mapped_column(String, default="general")
    tags: Mapped[str] = mapped_column(String, default="")  # comma-separated
    is_public: Mapped[bool] = mapped_column(default=True)

    # Pricing (optional - for premium templates)
    price_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "config": self.config,
            "category": self.category,
            "tags": self.tags.split(",") if self.tags else [],
            "is_public": self.is_public,
            "price_id": self.price_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
