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
    supabase_key: str = Field(
        default_factory=lambda: (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
            or ""
        ).strip()
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "").split(",")
            if origin.strip()
        ]
    )
    birdeye_api_key: str = Field(default_factory=lambda: os.getenv("BIRDEYE_API_KEY", "").strip())
    birdeye_chain: str = Field(default_factory=lambda: os.getenv("BIRDEYE_CHAIN", "solana").strip())
    birdeye_price_address: str = Field(
        default_factory=lambda: os.getenv(
            "BIRDEYE_PRICE_ADDRESS",
            "So11111111111111111111111111111111111111112",
        ).strip()
    )
    birdeye_price_currency: str = Field(
        default_factory=lambda: os.getenv("BIRDEYE_PRICE_CURRENCY", "usd").strip()
    )
    birdeye_chart_type: str = Field(default_factory=lambda: os.getenv("BIRDEYE_CHART_TYPE", "1m").strip())
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", "").strip())

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
        return bool(self.supabase_url and self.supabase_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Always include production frontend + local dev origins to avoid lockout via env overrides.
    required_origins = {
        "https://rekto.fun",
        "https://www.rekto.fun",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    }
    configured_origins = set(settings.cors_origins)
    settings.cors_origins = sorted(configured_origins.union(required_origins))
    return settings


# Global settings instance for backward compatibility
settings = get_settings()


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY)."
        )
    return create_client(settings.supabase_url, settings.supabase_key)


def get_supabase() -> Client:
    try:
        return get_supabase_client()
    except RuntimeError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc)) from exc