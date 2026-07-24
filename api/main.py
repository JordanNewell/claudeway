"""
Claudeway API - Main Entry Point

FastAPI application that provides the control plane for the core orchestration engine.

DEPRECATED PLATFORM FEATURES:
The following features have been moved to platform-deprecated/ and are NOT active:
- Multi-tenancy (tenants/)
- Billing (billing/)
- Templates (templates/)
- Analytics (analytics/)
- Gateway (gateway/)

These features were built before proving the core worked. They can be re-enabled later
when there are actual users to justify the complexity.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Platform config (still needed for CORS, etc)
from config import settings

# NOTE: Database init removed - deprecated features not needed
# from database import init_db, close_db
# from middleware import TenantContextMiddleware, RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan - startup and shutdown events."""
    # Startup
    print("Starting Claudeway API...")

    # Initialize the Runtime (core orchestration engine)
    from api.state import get_runtime
    runtime = get_runtime()
    await runtime.start()
    print("[OK] Claudeway Runtime initialized")

    # NOTE: Database and deprecated platform features NOT initialized
    # See platform-deprecated/ folder for multi-tenancy, billing, templates

    yield

    # Shutdown
    print("Shutting down Claudeway API...")
    await runtime.stop()
    print("[OK] Runtime stopped")


# Create FastAPI app
app = FastAPI(
    title="Claudeway API",
    description="Claude-native agent infrastructure platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: TenantContextMiddleware and RateLimitMiddleware disabled
# These depend on deprecated platform features (tenants, billing)
# Re-enable when platform features are re-activated
# app.add_middleware(TenantContextMiddleware)
# app.add_middleware(RateLimitMiddleware)


# Health check
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


# Debug endpoint to check runtime state
@app.get("/debug/state")
async def debug_state() -> dict[str, Any]:
    """Debug endpoint to check application state."""
    from api.state import get_runtime

    runtime = get_runtime()
    return runtime.get_status()


# Include routers
# NOTE: Only agents router is active - other routes moved to platform-deprecated/
from api.agents import router as agents_router

app.include_router(agents_router, prefix="/v1/agents", tags=["agents"])

# Deprecated platform routes (NOT active):
# from platform_deprecated.tenants import router as tenants_router
# from platform_deprecated.billing import router as billing_router
# from platform_deprecated.templates import router as templates_router
# app.include_router(tenants_router, prefix="/v1/tenants", tags=["tenants"])
# app.include_router(billing_router, prefix="/v1/billing", tags=["billing"])
# app.include_router(templates_router, prefix="/v1/templates", tags=["templates"])


# Root endpoint
@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "name": "Claudeway API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc) -> JSONResponse:
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    # Use app directly instead of string import (avoids reload issues)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disable reload for simpler startup
    )
