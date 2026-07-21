"""
User API routes for CRUD operations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import EmailStr
from supabase import Client

from models.user import (
    AcceptReferralRequest,
    ReferralRedemptionRequest,
    ReferralHistoryResponse,
    FollowRequest,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    LeaderboardResponse,
    UsernameCheckResponse,
    UserProfileResponse,
)
from services.database import get_request_db_client as get_db_client
from services.user_service import get_user_service, UserService
from services.leaderboard_service import LeaderboardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

PROFILE_USER_FIELDS = (
    "id,username,pubkey,profile_image,bio,twitter_username,created_at,"
    "followers,following,user_type"
)


def _is_username_unique_violation(error: Exception) -> bool:
    """Identify the PostgreSQL unique-index error as a race-condition fallback."""
    error_text = str(error).lower()
    return (
        "user_username_unique_idx" in error_text
        or ("duplicate key" in error_text and "username" in error_text)
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Create a new user with the provided data, or return existing user if pubkey already exists"
)
async def create_user(
    user_data: UserCreate,
    db: Client = Depends(get_db_client)
):
    """
    Create a new user.
    
    If a pubkey is provided and a user with that pubkey already exists,
    the existing user is returned instead of creating a duplicate.
    
    - **username**: User's display name (optional)
    - **email**: User's email address (optional)
    - **pubkey**: User's Solana public key (optional)
    - **profile_image**: URL to user's profile image (optional)
    - **bio**: User's bio/description (optional)
    """
    print(f"user data: {user_data}")
    service = get_user_service(db)
    try:
        if user_data.pubkey:
            existing_user = await service.get_user_by_pubkey(user_data.pubkey)
            if existing_user:
                logger.info(f"User with pubkey {user_data.pubkey} already exists, returning existing user")
                return existing_user
        if user_data.username and await service.username_exists(user_data.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken"
            )
        created_user = await service.create_user(user_data)
        if user_data.referrer_code:
            try:
                return await service.accept_referral(created_user.pubkey or "", user_data.referrer_code)
            except ValueError as referral_error:
                logger.warning(f"User created but referral was not applied: {referral_error}")

        return created_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        if _is_username_unique_violation(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken"
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


@router.get(
    "",
    response_model=UserListResponse,
    summary="List all users",
    description="Get a paginated list of all users"
)
async def list_users(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    search: Optional[str] = Query(None, max_length=100, description="Search username, email, or wallet"),
    db: Client = Depends(get_db_client)
):
    """
    List all users with pagination.
    
    - **limit**: Maximum number of users to return (default: 100, max: 1000)
    - **offset**: Number of users to skip for pagination (default: 0)
    """
    service = get_user_service(db)
    try:
        users = await service.list_users(limit=limit, offset=offset, search=search)
        total = await service.count_users(search=search)
        return UserListResponse(users=users, total=total)
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )


@router.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
    summary="Get challenge performance leaderboard",
    description="Get realized wins, losses, P&L and volume for resolved challenges"
)
async def get_leaderboard(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    period: str = Query("all", pattern="^(1d|7d|30d|all)$"),
    search: Optional[str] = Query(None, max_length=100),
    sort: str = Query("pnl", pattern="^(rank|created_challenges|win_rate|won|lost|pnl|volume)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    verification: str = Query("all", pattern="^(all|x|kol)$"),
    db: Client = Depends(get_db_client)
):
    """
    Get users for leaderboard displays.
    """
    try:
        return await LeaderboardService(db).get_leaderboard(
            period=period, limit=limit, offset=offset, search=search,
            sort=sort, order=order, verification=verification,
        )
    except Exception as e:
        logger.error(f"Failed to get leaderboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve leaderboard"
        )


@router.get(
    "/referral-leaderboard",
    response_model=UserListResponse,
    summary="Get the top referrers",
)
async def get_referral_leaderboard(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Client = Depends(get_db_client),
):
    """Rank users by successful referrals, independent of trading activity."""
    try:
        users = []
        page_size = 1000
        start = 0
        while True:
            batch = (
                db.table("user")
                .select("*")
                .range(start, start + page_size - 1)
                .execute()
                .data
                or []
            )
            users.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size

        users.sort(
            key=lambda item: (
                -(len(item.get("referrals") or [])),
                str(item.get("created_at") or ""),
                int(item.get("id") or 0),
            )
        )
        return UserListResponse(users=users[offset:offset + limit], total=len(users))
    except Exception as exc:
        logger.error("Failed to get referral leaderboard: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve referral leaderboard",
        ) from exc


@router.get(
    "/profile/{pubkey}",
    response_model=UserProfileResponse,
    summary="Get the compact public profile payload",
)
async def get_user_profile(pubkey: str, db: Client = Depends(get_db_client)):
    try:
        result = db.table("user").select(PROFILE_USER_FIELDS).eq("pubkey", pubkey).limit(1).execute()
        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user = result.data[0]
        leaderboard = await LeaderboardService(db).get_leaderboard(
            period="all", limit=1, offset=0, search=pubkey, sort="pnl", order="desc"
        )
        rows = leaderboard.get("users") if isinstance(leaderboard, dict) else []
        matching = next(
            (row for row in (rows or []) if str(row.get("pubkey") or row.get("wallet_address") or "").lower() == pubkey.lower()),
            {},
        )
        user["metrics"] = {
            key: matching.get(key, 0)
            for key in ("won", "lost", "win_rate", "pnl", "volume")
        }
        return user
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get profile for %s: %s", pubkey, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve profile") from exc


@router.get(
    "/by-pubkey/{pubkey}",
    response_model=UserResponse,
    summary="Get user by public key",
    description="Retrieve a user by their Solana public key"
)
async def get_user_by_pubkey(
    pubkey: str,
    db: Client = Depends(get_db_client)
):
    """
    Get a user by their Solana public key.
    
    - **pubkey**: The Solana public key of the user
    """
    service = get_user_service(db)
    try:
        user = await service.get_user_by_pubkey(pubkey)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with pubkey {pubkey} not found"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user by pubkey {pubkey}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )


@router.post(
    "/accept-referral",
    response_model=UserResponse,
    summary="Accept a referral code",
    description="Attach a referrer to a user and add the user to the referrer's referral list"
)
async def accept_referral(
    referral_data: AcceptReferralRequest,
    db: Client = Depends(get_db_client)
):
    """
    Accept a referral code for an existing user.
    """
    service = get_user_service(db)
    try:
        return await service.accept_referral(
            referral_data.new_user_wallet,
            referral_data.referrer_code,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to accept referral: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept referral"
        )


@router.post("/referral-redemptions", response_model=UserResponse)
async def request_referral_redemption(
    redemption: ReferralRedemptionRequest,
    db: Client = Depends(get_db_client),
):
    try:
        return await get_user_service(db).request_referral_redemption(redemption.wallet_address)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Failed to create referral redemption request: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create redemption request")


@router.get("/referral-history/{wallet_address}", response_model=ReferralHistoryResponse)
async def get_referral_history(
    wallet_address: str,
    db: Client = Depends(get_db_client),
):
    try:
        return await get_user_service(db).get_referral_history(wallet_address)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Failed to load referral history: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load referral history")


@router.post("/{target_wallet}/follow", response_model=UserResponse)
async def follow_user(
    target_wallet: str,
    follow_data: FollowRequest,
    db: Client = Depends(get_db_client),
):
    try:
        return await get_user_service(db).set_following(
            follow_data.follower_wallet, target_wallet, follow=True
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to follow user {target_wallet}: {e}")
        raise HTTPException(status_code=500, detail="Failed to follow user")


@router.delete("/{target_wallet}/follow", response_model=UserResponse)
async def unfollow_user(
    target_wallet: str,
    follow_data: FollowRequest,
    db: Client = Depends(get_db_client),
):
    try:
        return await get_user_service(db).set_following(
            follow_data.follower_wallet, target_wallet, follow=False
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to unfollow user {target_wallet}: {e}")
        raise HTTPException(status_code=500, detail="Failed to unfollow user")


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Retrieve a specific user by their ID"
)
async def get_user(
    user_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Get a user by their ID.
    
    - **user_id**: The unique ID of the user
    """
    service = get_user_service(db)
    try:
        user = await service.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )


@router.get(
    "/by-email/{email}",
    response_model=UserResponse,
    summary="Get user by email",
    description="Retrieve a user by their email address"
)
async def get_user_by_email(
    email: EmailStr,
    db: Client = Depends(get_db_client)
):
    """
    Get a user by their email address.
    
    - **email**: The email address of the user
    """
    service = get_user_service(db)
    try:
        user = await service.get_user_by_email(str(email))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email {email} not found"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user by email {email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )


@router.get(
    "/check-username/{username}",
    response_model=UsernameCheckResponse,
    summary="Check if a username exists",
    description="Check whether a given username is already taken"
)
async def check_username(
    username: str,
    db: Client = Depends(get_db_client)
):
    """
    Check whether a username already exists.

    - **username**: The username to check
    """
    service = get_user_service(db)
    try:
        exists = await service.username_exists(username)
        return UsernameCheckResponse(username=username, exists=exists)
    except Exception as e:
        logger.error(f"Failed to check username {username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check username"
        )


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user",
    description="Update an existing user's data"
)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Client = Depends(get_db_client)
):
    """
    Update a user by ID. Only provided fields will be updated.
    
    - **user_id**: The unique ID of the user to update
    - **username**: User's new display name (optional)
    - **email**: User's new email address (optional)
    - **pubkey**: User's new Solana public key (optional)
    - **profile_image**: New URL to user's profile image (optional)
    - **bio**: User's new bio/description (optional)
    """
    service = get_user_service(db)
    try:
        if user_data.username:
            existing_user = await service.get_user_by_username(user_data.username)
            if existing_user and existing_user.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This username is already taken"
                )

        user = await service.update_user(user_id, user_data)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user {user_id}: {e}")
        if _is_username_unique_violation(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken"
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete a user by their ID"
)
async def delete_user(
    user_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Delete a user by their ID.
    
    - **user_id**: The unique ID of the user to delete
    """
    service = get_user_service(db)
    try:
        deleted = await service.delete_user(user_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )
