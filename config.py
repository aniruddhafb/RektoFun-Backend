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

    supabase_url: str = Field(default_factory=lambda: os.getenv("SUPABASE_URL", "").strip())
    supabase_key: str = Field(
        default_factory=lambda: (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
            or ""
        ).strip()
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS",
                "*",
            ).split(",")
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


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if "*" in settings.cors_origins:
        settings.cors_origins = ["*"]
        return settings

    # Always include local frontend/dev origins to avoid accidental lockout via env overrides.
    required_dev_origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }
    settings.cors_origins = sorted(set(settings.cors_origins).union(required_dev_origins))
    return settings


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
