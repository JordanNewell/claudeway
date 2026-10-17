"""Templates module."""
from templates.models import Template
from templates.router import router
from templates.service import BUILTIN_TEMPLATES, TemplateService

__all__ = ["Template", "TemplateService", "BUILTIN_TEMPLATES", "router"]
