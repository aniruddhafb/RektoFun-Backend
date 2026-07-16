"""Application configuration, settings, and database client."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client, create_client

load_dotenv()


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # API Settings
    app_name: str = Field(default="RektoFun API")
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    supabase_url: str = Field(default_factory=lambda: os.getenv("SUPABASE_URL", "").strip())
    supabase_service_role_key: str = Field(
        default_factory=lambda: (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_KEY")
            or ""
        ).strip()
    )
    supabase_anon_key: str = Field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", "").strip())
    use_supabase_anon_reads: bool = Field(
        default_factory=lambda: os.getenv("USE_SUPABASE_ANON_READS", "false").lower() == "true"
    )
    internal_api_key: str = Field(
        default_factory=lambda: (os.getenv("INTERNAL_API_KEY") or os.getenv("CRON_API_KEY") or "").strip()
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "https://rekto.fun",
            "https://www.rekto.fun",
            "https://devnet.rekto.fun",
            "https://devnet-api.rekto.fun",
            "http://localhost:3000",
            "https://sports.rekto.fun",
            "https://api.rekto.fun",
            "https://settlements.rekto.fun",
        ]
    )
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", "").strip())
    settlement_service_url: str = Field(
        default_factory=lambda: os.getenv("SETTLEMENT_API", "").strip()
    )
    settlement_api_secret: str = Field(
        default_factory=lambda: os.getenv("SETTLEMENT_API_SECRET", "").strip()
    )

    # Email configuration
    smtp_server: str = Field(default_factory=lambda: os.getenv("SMTP_SERVER", "smtp.gmail.com").strip())
    smtp_port: int = Field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = Field(default_factory=lambda: os.getenv("SMTP_USER", "").strip())
    smtp_password: str = Field(default_factory=lambda: os.getenv("SMTP_PASSWORD", "").strip())
    email_from: str = Field(
        default_factory=lambda: os.getenv("EMAIL_FROM", "RektoFun <verify@rekto.fun>").strip()
    )

    @property
    def is_configured(self) -> bool:
        """Check if required Supabase configuration is present"""
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_service_supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "Supabase service access is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@lru_cache
def get_public_supabase_client() -> Client:
    settings = get_settings()
    if settings.use_supabase_anon_reads and settings.supabase_url and settings.supabase_anon_key:
        return create_client(settings.supabase_url, settings.supabase_anon_key)
    # Compatibility mode until public SELECT RLS policies have been deployed and
    # USE_SUPABASE_ANON_READS=true is explicitly enabled.
    import logging
    logging.getLogger(__name__).warning(
        "Anon reads are disabled; public reads temporarily use the service client"
    )
    return get_service_supabase_client()


# Backwards-compatible alias for internal services.
get_supabase_client = get_service_supabase_client


def get_supabase() -> Client:
    try:
        return get_service_supabase_client()
    except RuntimeError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc)) from exc
