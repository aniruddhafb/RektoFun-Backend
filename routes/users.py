"""User API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from config import get_supabase
from models.user import UserCreate, UserListResponse, UserResponse, UserUpdate
from utils import serialize_payload

router = APIRouter(prefix="/users", tags=["users"])


def coerce_user(row: dict) -> UserResponse:
    return UserResponse.model_validate(row)


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    user: UserCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    """
    Create a new user. If a user with the same wallet_address already exists,
    returns the existing user instead of creating a duplicate.

    Example:
        curl -X POST http://localhost:8000/users \\
          -H "Content-Type: application/json" \\
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
            return coerce_user(existing_user.data[0])
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

    return coerce_user(result.data[0])


@router.get("", response_model=UserListResponse)
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
        users=[coerce_user(row) for row in rows],
        count=len(rows),
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user_by_id(
    user_id: UUID,
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

    return coerce_user(rows[0])


@router.get("/wallet/{wallet_address}", response_model=UserResponse)
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

    return coerce_user(rows[0])


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    user_update: UserUpdate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    """
    Update a user's profile information.

    Example:
        curl -X PATCH http://localhost:8000/users/123e4567-e89b-12d3-a456-426614174000 \\
          -H "Content-Type: application/json" \\
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

    return coerce_user(result.data[0])


@router.delete("/{user_id}", status_code=204, response_model=None)
def delete_user(
    user_id: UUID,
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