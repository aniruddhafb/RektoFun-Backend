"""
RektoFun Backend API

FastAPI + Supabase backend for persisting challenge metadata after a
successful Solana transaction.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client, create_client

load_dotenv()


class ChallengeStatus(str, Enum):
    open = "open"
    active = "active"
    settled = "settled"
    cancelled = "cancelled"


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
                "http://localhost:3000,http://127.0.0.1:3000",
            ).split(",")
            if origin.strip()
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


app = FastAPI(title="RektoFun API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChallengeCreate(BaseModel):
    tx_signature: str = Field(min_length=1)
    challenge_pda: str = Field(min_length=1)
    challenge_id: int = Field(ge=0)
    creator_wallet: str = Field(min_length=1)
    market: str = Field(default="SOL-PERP", min_length=1)
    asset: str = Field(min_length=1)
    bet_amount_sol: float = Field(gt=0)
    target_price_usd_cents: int = Field(gt=0)
    direction_above: bool
    expires_at: int = Field(gt=0)
    resolves_at: int = Field(gt=0)


class ChallengeResponse(BaseModel):
    id: int
    tx_signature: str
    challenge_pda: str
    challenge_id: int
    creator_wallet: str
    market: str
    asset: str
    bet_amount_sol: float
    target_price_usd_cents: int
    direction_above: bool
    expires_at: int
    resolves_at: int
    status: ChallengeStatus
    created_at: datetime
    updated_at: datetime


class ChallengeListResponse(BaseModel):
    challenges: list[ChallengeResponse]
    count: int


def _coerce_challenge(row: dict) -> ChallengeResponse:
    return ChallengeResponse.model_validate(row)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "RektoFun API is running", "version": "1.0.0"}


@app.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "supabase_configured": bool(settings.supabase_url and settings.supabase_key),
    }


@app.post("/challenges", response_model=ChallengeResponse, status_code=201)
def create_challenge(
    challenge: ChallengeCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeResponse:
    if challenge.resolves_at <= challenge.expires_at:
        raise HTTPException(
            status_code=422,
            detail="resolves_at must be greater than expires_at",
        )

    payload = {
        **challenge.model_dump(),
        "status": ChallengeStatus.open.value,
    }

    try:
        result = (
            supabase.table("challenges")
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to insert challenge: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to insert challenge")

    return _coerce_challenge(result.data[0])


@app.get("/challenges", response_model=ChallengeListResponse)
def get_challenges(
    supabase: Annotated[Client, Depends(get_supabase)],
    status: ChallengeStatus | None = None,
    asset: str | None = None,
    creator_wallet: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChallengeListResponse:
    query = supabase.table("challenges").select("*")

    if status is not None:
        query = query.eq("status", status.value)
    if asset:
        query = query.eq("asset", asset)
    if creator_wallet:
        query = query.eq("creator_wallet", creator_wallet)

    try:
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenges: {exc}",
        ) from exc

    rows = result.data or []
    return ChallengeListResponse(
        challenges=[_coerce_challenge(row) for row in rows],
        count=len(rows),
    )


@app.get("/challenges/{challenge_id}", response_model=ChallengeResponse)
def get_challenge_by_id(
    challenge_id: int,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeResponse:
    try:
        result = (
            supabase.table("challenges")
            .select("*")
            .eq("id", challenge_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Challenge not found")

    return _coerce_challenge(rows[0])


@app.get("/challenges/pda/{challenge_pda}", response_model=ChallengeResponse)
def get_challenge_by_pda(
    challenge_pda: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeResponse:
    try:
        result = (
            supabase.table("challenges")
            .select("*")
            .eq("challenge_pda", challenge_pda)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Challenge not found")

    return _coerce_challenge(rows[0])
