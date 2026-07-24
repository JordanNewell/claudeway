"""
Claudeway Middleware

Custom middleware for tenant context and rate limiting.
"""

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import redis.asyncio as redis

from config import settings


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract tenant context from request headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        # Extract tenant_id from header or query param
        tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")

        # Add to request state for use in endpoints
        request.state.tenant_id = tenant_id

        response = await call_next(request)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._redis: redis.Redis | None = None

    @property
    def redis(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        # Skip rate limiting for health check
        if request.url.path == "/health":
            return await call_next(request)

        # Get identifier (tenant_id or IP)
        tenant_id = getattr(request.state, "tenant_id", None) or request.client.host
        key = f"ratelimit:{tenant_id}"

        try:
            # Check rate limit
            current = await self.redis.incr(key)

            if current == 1:
                # Set expiry on first request
                await self.redis.expire(key, settings.rate_limit_period)

            if current > settings.rate_limit_requests:
                return Response(
                    content='{"error": "Rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                )

        except Exception:
            # Fail open - if Redis is down, allow requests
            pass

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
        response.headers["X-RateLimit-Period"] = str(settings.rate_limit_period)

        return response
