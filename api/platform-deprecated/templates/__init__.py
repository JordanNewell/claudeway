"""Templates module."""
from templates.models import Template
from templates.service import TemplateService, BUILTIN_TEMPLATES
from templates.router import router

__all__ = ["Template", "TemplateService", "BUILTIN_TEMPLATES", "router"]
