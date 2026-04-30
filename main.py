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
# from uuid import UUID

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client, create_client

load_dotenv()


class ChallengeStatus(str, Enum):
    open = "open"
    locked = "locked"
    resolved = "resolved"
    cancelled = "cancelled"


class EventType(str, Enum):
    binary = "binary"
    multi_outcome = "multi_outcome"
    numeric_range = "numeric_range"


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
                "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:8000",
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


# =============================================================================
# Challenge Models
# =============================================================================


class ChallengeCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    category: str = Field(min_length=1)
    subcategory: str | None = None
    event_type: EventType
    ticker: str | None = None
    created_by: str | None = None
    resolution_source: str | None = None
    resolution_details: dict | None = None
    expire_time: datetime
    resolve_time: datetime | None = None
    result: dict | None = None
    metadata: dict | None = None


class ChallengeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    event_type: EventType | None = None
    ticker: str | None = None
    status: ChallengeStatus | None = None
    resolution_source: str | None = None
    resolution_details: dict | None = None
    expire_time: datetime | None = None
    resolve_time: datetime | None = None
    result: dict | None = None
    metadata: dict | None = None


class ChallengeResponse(BaseModel):
    id: str
    title: str
    description: str | None
    category: str
    subcategory: str | None
    event_type: str
    ticker: str | None
    created_by: str | None
    status: str
    resolution_source: str | None
    resolution_details: dict | None
    expire_time: datetime
    resolve_time: datetime | None
    result: dict | None
    metadata: dict | None
    created_at: datetime | None
    updated_at: datetime | None


class ChallengeListResponse(BaseModel):
    challenges: list[ChallengeResponse]
    count: int


# =============================================================================
# Challenge Outcome Models
# =============================================================================


class ChallengeOutcomeCreate(BaseModel):
    challenge_id: str = Field(min_length=1)
    outcome_key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    metadata: dict | None = None


class ChallengeOutcomeResponse(BaseModel):
    id: str
    challenge_id: str
    outcome_key: str
    title: str
    metadata: dict | None
    created_at: datetime | None


class ChallengeOutcomeListResponse(BaseModel):
    outcomes: list[ChallengeOutcomeResponse]
    count: int


def _coerce_challenge(row: dict) -> ChallengeResponse:
    return ChallengeResponse.model_validate(row)


def _serialize_payload(data: dict) -> dict:
    """Convert datetime objects to ISO format strings for JSON serialization."""
    result = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


# =============================================================================
# User Models
# =============================================================================


class UserCreate(BaseModel):
    wallet_address: str = Field(min_length=1)
    username: str | None = None
    description: str | None = None
    profile_image: str | None = None
    login_type: str = Field(default="wallet", min_length=1)
    referral_code: str | None = None
    referred_by: str | None = None


class UserUpdate(BaseModel):
    username: str | None = None
    description: str | None = None
    profile_image: str | None = None


class UserResponse(BaseModel):
    id: str
    wallet_address: str
    username: str | None
    description: str | None
    profile_image: str | None
    login_type: str
    referral_code: str | None
    referred_by: str | None
    referrals: list[str]
    created_at: datetime | None
    updated_at: datetime | None
    earnings: float | None


class UserListResponse(BaseModel):
    users: list[UserResponse]
    count: int


def _coerce_user(row: dict) -> UserResponse:
    return UserResponse.model_validate(row)


# =============================================================================
# User CRUD Endpoints
# =============================================================================


@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    user: UserCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    """
    Create a new user. If a user with the same wallet_address already exists,
    returns the existing user instead of creating a duplicate.

    Example:
        curl -X POST http://localhost:8000/users \
          -H "Content-Type: application/json" \
          -d '{
            "wallet_address": "7YkS7x...example",
            "username": "crypto_trader",
            "description": "Passionate about crypto",
            "login_type": "wallet"
          }'
    """
    # Check if user with this wallet_address already exists
    try:
        existing_user = (
            supabase.table("users")
            .select("*")
            .eq("wallet_address", user.wallet_address)
            .limit(1)
            .execute()
        )
        if existing_user.data:
            return _coerce_user(existing_user.data[0])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing user: {exc}",
        ) from exc

    payload = {
        "wallet_address": user.wallet_address,
        "username": user.username,
        "description": user.description,
        "profile_image": user.profile_image,
        "login_type": user.login_type,
    }

    # If referral code is provided, find the referrer
    if user.referred_by:
        try:
            referrer_result = (
                supabase.table("users")
                .select("id")
                .eq("referral_code", user.referred_by)
                .limit(1)
                .execute()
            )
            if referrer_result.data:
                payload["referred_by"] = referrer_result.data[0]["id"]
        except Exception:
            pass  # Ignore referral lookup errors

    try:
        result = (
            supabase.table("users")
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create user: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create user")

    return _coerce_user(result.data[0])


@app.get("/users", response_model=UserListResponse)
def get_users(
    supabase: Annotated[Client, Depends(get_supabase)],
    wallet_address: str | None = None,
    username: str | None = None,
    referral_code: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListResponse:
    """
    Get a list of users with optional filters.

    Example:
        curl "http://localhost:8000/users?wallet_address=7YkS7x...example&limit=10"
    """
    query = supabase.table("users").select("*")

    if wallet_address:
        query = query.eq("wallet_address", wallet_address)
    if username:
        query = query.eq("username", username)
    if referral_code:
        query = query.eq("referral_code", referral_code)

    try:
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch users: {exc}",
        ) from exc

    rows = result.data or []
    return UserListResponse(
        users=[_coerce_user(row) for row in rows],
        count=len(rows),
    )


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user_by_id(
    user_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    """
    Get a user by their ID.

    Example:
        curl http://localhost:8000/users/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        result = (
            supabase.table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="User not found")

    return _coerce_user(rows[0])


@app.get("/users/wallet/{wallet_address}", response_model=UserResponse)
def get_user_by_wallet(
    wallet_address: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    """
    Get a user by their wallet address.

    Example:
        curl http://localhost:8000/users/wallet/7YkS7x...example
    """
    try:
        result = (
            supabase.table("users")
            .select("*")
            .eq("wallet_address", wallet_address)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="User not found")

    return _coerce_user(rows[0])


@app.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user_update: UserUpdate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    """
    Update a user's profile information.

    Example:
        curl -X PATCH http://localhost:8000/users/123e4567-e89b-12d3-a456-426614174000 \
          -H "Content-Type: application/json" \
          -d '{
            "username": "new_username",
            "description": "Updated bio"
          }'
    """
    # First check if user exists
    try:
        existing = (
            supabase.table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="User not found")

    # Build update payload (only non-None fields)
    update_payload = {k: v for k, v in user_update.model_dump().items() if v is not None}

    if not update_payload:
        raise HTTPException(
            status_code=422,
            detail="No fields to update",
        )

    try:
        result = (
            supabase.table("users")
            .update(update_payload)
            .eq("id", user_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update user: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update user")

    return _coerce_user(result.data[0])


@app.delete("/users/{user_id}", status_code=204, response_model=None)
def delete_user(
    user_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    """
    Delete a user by their ID.

    Example:
        curl -X DELETE http://localhost:8000/users/123e4567-e89b-12d3-a456-426614174000
    """
    # First check if user exists
    try:
        existing = (
            supabase.table("users")
            .select("id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        supabase.table("users").delete().eq("id", user_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete user: {exc}",
        ) from exc


@app.get("/")
def root() -> dict[str, str]:
    """
    Example:
        curl http://localhost:8000/
    """
    return {"message": "RektoFun API is running", "version": "1.0.0"}


@app.get("/health/supabase-env")
def health():
    return {
        "SUPABASE_URL_set": bool(os.getenv("SUPABASE_URL")),
        "SUPABASE_SERVICE_ROLE_KEY_set": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        "SUPABASE_ANON_KEY_set": bool(os.getenv("SUPABASE_ANON_KEY")),
    }


# @app.get("/health")
# def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
#     """
#     Example:
#         curl http://localhost:8000/health
#     """
#     return {
#         "status": "ok",
#         "timestamp": datetime.now(timezone.utc).isoformat(),
#         "supabase_configured": bool(settings.supabase_url and settings.supabase_key),
#     }


# =============================================================================
# Challenge CRUD Endpoints
# =============================================================================


@app.post("/challenges", response_model=ChallengeResponse, status_code=201)
def create_challenge(
    challenge: ChallengeCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeResponse:
    """
    Create a new challenge.

    Example:
        curl -X POST http://localhost:8000/challenges \\
          -H "Content-Type: application/json" \\
          -d '{
            "title": "Will BTC reach $100k by end of 2025?",
            "description": "Binary prediction market for Bitcoin price",
            "category": "crypto",
            "subcategory": "btc",
            "event_type": "binary",
            "ticker": "BTC",
            "created_by": "user-uuid-here",
            "expire_time": "2025-12-31T23:59:59Z",
            "resolve_time": "2026-01-01T12:00:00Z"
          }'
    """
    payload = _serialize_payload({
        **challenge.model_dump(),
        "status": ChallengeStatus.open.value,
    })

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
    category: str | None = None,
    ticker: str | None = None,
    created_by: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChallengeListResponse:
    """
    Get a list of challenges with optional filters.

    Example:
        curl "http://localhost:8000/challenges?status=open&category=crypto&ticker=BTC&limit=10&offset=0"
    """
    query = supabase.table("challenges").select("*")

    if status is not None:
        query = query.eq("status", status.value)
    if category:
        query = query.eq("category", category)
    if ticker:
        query = query.eq("ticker", ticker)
    if created_by:
        query = query.eq("created_by", created_by)

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
    challenge_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeResponse:
    """
    Get a challenge by its ID.

    Example:
        curl http://localhost:8000/challenges/123e4567-e89b-12d3-a456-426614174000
    """
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


@app.patch("/challenges/{challenge_id}", response_model=ChallengeResponse)
def update_challenge(
    challenge_id: str,
    challenge_update: ChallengeUpdate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeResponse:
    """
    Update a challenge.

    Example:
        curl -X PATCH http://localhost:8000/challenges/123e4567-e89b-12d3-a456-426614174000 \\
          -H "Content-Type: application/json" \\
          -d '{"status": "resolved", "result": {"outcome": "YES"}}'
    """
    # First check if challenge exists
    try:
        existing = (
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

    if not existing.data:
        raise HTTPException(status_code=404, detail="Challenge not found")

    # Build update payload (only non-None fields)
    update_payload = {k: v for k, v in challenge_update.model_dump().items() if v is not None}
    update_payload = _serialize_payload(update_payload)

    if not update_payload:
        raise HTTPException(
            status_code=422,
            detail="No fields to update",
        )

    try:
        result = (
            supabase.table("challenges")
            .update(update_payload)
            .eq("id", challenge_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update challenge: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update challenge")

    return _coerce_challenge(result.data[0])


@app.delete("/challenges/{challenge_id}", status_code=204, response_model=None)
def delete_challenge(
    challenge_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    """
    Delete a challenge by its ID.

    Example:
        curl -X DELETE http://localhost:8000/challenges/123e4567-e89b-12d3-a456-426614174000
    """
    # First check if challenge exists
    try:
        existing = (
            supabase.table("challenges")
            .select("id")
            .eq("id", challenge_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Challenge not found")

    try:
        supabase.table("challenges").delete().eq("id", challenge_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete challenge: {exc}",
        ) from exc


# =============================================================================
# Challenge Outcome CRUD Endpoints
# =============================================================================


def _coerce_challenge_outcome(row: dict) -> ChallengeOutcomeResponse:
    return ChallengeOutcomeResponse.model_validate(row)


@app.post("/challenge-outcomes", response_model=ChallengeOutcomeResponse, status_code=201)
def create_challenge_outcome(
    outcome: ChallengeOutcomeCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeOutcomeResponse:
    """
    Create a new challenge outcome.

    Example:
        curl -X POST http://localhost:8000/challenge-outcomes \\
          -H "Content-Type: application/json" \\
          -d '{
            "challenge_id": "123e4567-e89b-12d3-a456-426614174000",
            "outcome_key": "YES",
            "title": "Yes - BTC reaches $100k"
          }'
    """
    # Check if challenge exists
    try:
        challenge = (
            supabase.table("challenges")
            .select("id")
            .eq("id", outcome.challenge_id)
            .limit(1)
            .execute()
        )
        if not challenge.data:
            raise HTTPException(status_code=404, detail="Challenge not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check challenge: {exc}",
        ) from exc

    payload = _serialize_payload(outcome.model_dump())

    try:
        result = (
            supabase.table("challenge_outcomes")
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to insert challenge outcome: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to insert challenge outcome")

    return _coerce_challenge_outcome(result.data[0])


@app.get("/challenge-outcomes", response_model=ChallengeOutcomeListResponse)
def get_challenge_outcomes(
    supabase: Annotated[Client, Depends(get_supabase)],
    challenge_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChallengeOutcomeListResponse:
    """
    Get a list of challenge outcomes with optional filters.

    Example:
        curl "http://localhost:8000/challenge-outcomes?challenge_id=123e4567-e89b-12d3-a456-426614174000&limit=10"
    """
    query = supabase.table("challenge_outcomes").select("*")

    if challenge_id:
        query = query.eq("challenge_id", challenge_id)

    try:
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge outcomes: {exc}",
        ) from exc

    rows = result.data or []
    return ChallengeOutcomeListResponse(
        outcomes=[_coerce_challenge_outcome(row) for row in rows],
        count=len(rows),
    )


@app.get("/challenge-outcomes/{outcome_id}", response_model=ChallengeOutcomeResponse)
def get_challenge_outcome_by_id(
    outcome_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeOutcomeResponse:
    """
    Get a challenge outcome by its ID.

    Example:
        curl http://localhost:8000/challenge-outcomes/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        result = (
            supabase.table("challenge_outcomes")
            .select("*")
            .eq("id", outcome_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge outcome: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Challenge outcome not found")

    return _coerce_challenge_outcome(rows[0])


@app.delete("/challenge-outcomes/{outcome_id}", status_code=204, response_model=None)
def delete_challenge_outcome(
    outcome_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    """
    Delete a challenge outcome by its ID.

    Example:
        curl -X DELETE http://localhost:8000/challenge-outcomes/123e4567-e89b-12d3-a456-426614174000
    """
    # First check if outcome exists
    try:
        existing = (
            supabase.table("challenge_outcomes")
            .select("id")
            .eq("id", outcome_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge outcome: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Challenge outcome not found")

    try:
        supabase.table("challenge_outcomes").delete().eq("id", outcome_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete challenge outcome: {exc}",
        ) from exc