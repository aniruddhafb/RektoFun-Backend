"""
User API routes for CRUD operations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import EmailStr
from supabase import Client

from models.user import UserCreate, UserUpdate, UserResponse, UserListResponse, UsernameCheckResponse
from services.database import get_db_client
from services.user_service import get_user_service, UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


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
        return await service.create_user(user_data)
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
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
    db: Client = Depends(get_db_client)
):
    """
    List all users with pagination.
    
    - **limit**: Maximum number of users to return (default: 100, max: 1000)
    - **offset**: Number of users to skip for pagination (default: 0)
    """
    service = get_user_service(db)
    try:
        users = await service.list_users(limit=limit, offset=offset)
        total = await service.count_users()
        return UserListResponse(users=users, total=total)
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )


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
