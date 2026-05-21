"""User API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from supabase import Client

from config import get_supabase
from models.user import (
    FollowActionRequest,
    FollowStatusResponse,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
router = APIRouter(prefix="/users", tags=["users"])


def coerce_user(row: dict) -> UserResponse:
    return UserResponse.model_validate(row)


def find_user_by_wallet(
    supabase: Client,
    wallet_address: str,
) -> dict | None:
    result = (
        supabase.table("users")
        .select("*")
        .eq("wallet_address", wallet_address)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def normalize_wallet(wallet_address: str) -> str:
    return wallet_address.strip()


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
    try:
        wallet_address = normalize_wallet(user.wallet_address)
        existing_user = find_user_by_wallet(supabase, wallet_address)
        if existing_user:
            return coerce_user(existing_user)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing user: {exc}",
        ) from exc

    payload = {
        "wallet_address": wallet_address,
        "username": user.username,
        "description": user.description,
        "profile_image": user.profile_image,
        "login_type": user.login_type,
        "followers": [],
        "following": [],
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


@router.post("/wallet/{wallet_address}/ensure", response_model=UserResponse)
def ensure_user_by_wallet(
    wallet_address: str,
    supabase: Annotated[Client, Depends(get_supabase)],
    body: Annotated[dict | None, Body()] = None,
) -> UserResponse:
    """
    Ensure a user exists for a wallet address and return that user.
    This is optimized for navbar/session bootstrap to avoid create+fetch chains.
    """
    wallet_address = normalize_wallet(wallet_address)
    payload = body or {}
    login_type = payload.get("login_type", "wallet")
    username = payload.get("username") or f"user-{wallet_address[:8]}"
    description = payload.get("description")
    profile_image = payload.get("profile_image")

    try:
        existing_user = find_user_by_wallet(supabase, wallet_address)
        if existing_user:
            return coerce_user(existing_user)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing user: {exc}",
        ) from exc

    try:
        result = (
            supabase.table("users")
            .insert(
                {
                    "wallet_address": wallet_address,
                    "username": username,
                    "description": description,
                    "profile_image": profile_image,
                    "login_type": login_type,
                    "followers": [],
                    "following": [],
                }
            )
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create user: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to ensure user")

    return coerce_user(result.data[0])


@router.get("/leaderboard", response_model=UserListResponse)
def get_leaderboard(
    supabase: Annotated[Client, Depends(get_supabase)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: str | None = None,
) -> UserListResponse:
    """
    Get users ranked by referral count for the leaderboard.
    Returns users sorted by number of referrals (descending - most referrals first).
    Each user's points are calculated as: referral_count * 100

    Example:
        curl "http://localhost:8000/users/leaderboard?limit=10&offset=0"
        curl "http://localhost:8000/users/leaderboard?search=trader&limit=10&offset=0"
    """
    try:
        # Fetch all users with their referrals count
        # We need to order by the length of the referrals array
        # Supabase doesn't directly support ordering by array length,
        # so we fetch all and sort in Python
        result = (
            supabase.table("users")
            .select("*")
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch leaderboard: {exc}",
        ) from exc

    rows = result.data or []
    
    # Filter by username if search query is provided
    if search:
        search_lower = search.lower()
        rows = [row for row in rows if row.get("username") and search_lower in row.get("username", "").lower()]
    
    # Sort by referral count (descending - most referrals first)
    # Points = referral_count * 100
    sorted_rows = sorted(
        rows,
        key=lambda x: len(x.get("referrals") or []),
        reverse=True
    )
    
    # Apply pagination to sorted results
    paginated_rows = sorted_rows[offset:offset + limit]
    
    return UserListResponse(
        users=[coerce_user(row) for row in paginated_rows],
        count=len(sorted_rows),
    )


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
        row = find_user_by_wallet(supabase, normalize_wallet(wallet_address))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user: {exc}",
        ) from exc

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return coerce_user(row)


@router.get("/wallet/{wallet_address}/follow-status", response_model=FollowStatusResponse)
def get_follow_status(
    wallet_address: str,
    follower_wallet_address: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> FollowStatusResponse:
    target_wallet = normalize_wallet(wallet_address)
    follower_wallet = normalize_wallet(follower_wallet_address)

    target_user = find_user_by_wallet(supabase, target_wallet)
    follower_user = find_user_by_wallet(supabase, follower_wallet)

    if not target_user or not follower_user:
        return FollowStatusResponse(is_following=False)

    follower_id = str(follower_user["id"])
    followers = target_user.get("followers") or []
    return FollowStatusResponse(is_following=follower_id in followers)


@router.post("/wallet/{wallet_address}/follow", response_model=UserResponse)
def follow_user(
    wallet_address: str,
    body: FollowActionRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    target_wallet = normalize_wallet(wallet_address)
    follower_wallet = normalize_wallet(body.follower_wallet_address)

    if target_wallet == follower_wallet:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    target_user = find_user_by_wallet(supabase, target_wallet)
    follower_user = find_user_by_wallet(supabase, follower_wallet)

    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")
    if not follower_user:
        raise HTTPException(status_code=404, detail="Follower user not found")

    target_id = str(target_user["id"])
    follower_id = str(follower_user["id"])

    target_followers = target_user.get("followers") or []
    follower_following = follower_user.get("following") or []

    if follower_id not in target_followers:
        target_followers = [*target_followers, follower_id]
    if target_id not in follower_following:
        follower_following = [*follower_following, target_id]

    try:
        target_update = (
            supabase.table("users")
            .update({"followers": target_followers})
            .eq("id", target_id)
            .execute()
        )
        supabase.table("users").update({"following": follower_following}).eq("id", follower_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to follow user: {exc}") from exc

    if not target_update.data:
        raise HTTPException(status_code=500, detail="Failed to follow user")

    return coerce_user(target_update.data[0])


@router.post("/wallet/{wallet_address}/unfollow", response_model=UserResponse)
def unfollow_user(
    wallet_address: str,
    body: FollowActionRequest,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    target_wallet = normalize_wallet(wallet_address)
    follower_wallet = normalize_wallet(body.follower_wallet_address)

    if target_wallet == follower_wallet:
        raise HTTPException(status_code=400, detail="You cannot unfollow yourself")

    target_user = find_user_by_wallet(supabase, target_wallet)
    follower_user = find_user_by_wallet(supabase, follower_wallet)

    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")
    if not follower_user:
        raise HTTPException(status_code=404, detail="Follower user not found")

    target_id = str(target_user["id"])
    follower_id = str(follower_user["id"])

    target_followers = [uid for uid in (target_user.get("followers") or []) if uid != follower_id]
    follower_following = [uid for uid in (follower_user.get("following") or []) if uid != target_id]

    try:
        target_update = (
            supabase.table("users")
            .update({"followers": target_followers})
            .eq("id", target_id)
            .execute()
        )
        supabase.table("users").update({"following": follower_following}).eq("id", follower_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to unfollow user: {exc}") from exc

    if not target_update.data:
        raise HTTPException(status_code=500, detail="Failed to unfollow user")

    return coerce_user(target_update.data[0])


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


@router.post("/accept-referral", response_model=UserResponse)
def accept_referral(
    body: Annotated[dict, Body(...)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> UserResponse:
    """
    Accept a referral by linking the new user's wallet to a referrer.
    Both users must exist.

    Example:
        curl -X POST "http://localhost:8000/users/accept-referral" \\
          -H "Content-Type: application/json" \\
          -d '{"new_user_wallet": "7YkS7x...new", "referrer_wallet": "7YkS7x...ref"}'
    """
    new_user_wallet = body.get("new_user_wallet")
    referrer_code = body.get("referrer_code")

    if not new_user_wallet or not referrer_code:
        raise HTTPException(status_code=400, detail="new_user_wallet and referrer_code are required")

    # Find the new user
    try:
        new_user_result = (
            supabase.table("users")
            .select("*")
            .eq("wallet_address", new_user_wallet)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to find new user: {exc}",
        ) from exc

    if not new_user_result.data:
        raise HTTPException(status_code=404, detail="New user not found")

    new_user = new_user_result.data[0]

    # Find the referrer by their referral_code (not wallet address)
    try:
        referrer_result = (
            supabase.table("users")
            .select("*")
            .eq("referral_code", referrer_code)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to find referrer: {exc}",
        ) from exc

    if not referrer_result.data:
        raise HTTPException(status_code=404, detail="Referrer not found")

    referrer = referrer_result.data[0]

    # Update the new user's referred_by field to the referrer's user ID
    try:
        result = (
            supabase.table("users")
            .update({"referred_by": referrer["id"]})
            .eq("wallet_address", new_user_wallet)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to accept referral: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to accept referral")

    # Update the referrer's referrals list (append new user's ID)
    current_referrals = referrer.get("referrals", [])
    if new_user["id"] not in current_referrals:
        try:
            supabase.table("users").update(
                {"referrals": current_referrals + [new_user["id"]]}
            ).eq("id", referrer["id"]).execute()
        except Exception:
            pass  # Non-critical error, ignore

    return coerce_user(result.data[0])
