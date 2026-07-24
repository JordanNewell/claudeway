"""
Claudeway Configuration

Settings loaded from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_prefix="CLAUDWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
    ]

    # Database - DEPRECATED (not used by core runtime)
    # Re-enable when platform features (tenants, billing, templates) are restored
    database_url: str = "postgresql+asyncpg://claudeway:claudeway@localhost:5432/claudeway"

    # Redis - DEPRECATED (not used by core runtime)
    # Re-enable when rate limiting middleware is restored
    redis_url: str = "redis://localhost:6379/0"

    # Claude-Flow - DEPRECATED (replaced by custom core runtime)
    claude_flow_url: str = "http://localhost:8080"
    claude_flow_api_key: str = ""

    # NATS - DEPRECATED (not used by core runtime)
    # Current: Uses asyncio queues for in-process messaging
    # Re-enable if federated multi-process architecture is needed
    nats_url: str = "nats://localhost:4222"
    nats_user: str = ""
    nats_password: str = ""

    # JWT / Auth
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Stripe (billing)
    stripe_api_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_pro: str = ""
    stripe_price_id_enterprise: str = ""

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    # Usage limits (per tenant)
    free_tier_agents: int = 1
    pro_tier_agents: int = 10
    enterprise_tier_agents: int = -1  # unlimited

    # Anthropic (for direct SDK usage if needed)
    anthropic_api_key: str = ""


# Global settings instance
settings = Settings()
