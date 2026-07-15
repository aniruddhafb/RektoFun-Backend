"""
Position API routes for CRUD operations.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from models.position import (
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    PositionListResponse,
    Side
)
from services.database import get_db_client
from services.position_service import get_position_service, PositionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/positions", tags=["positions"])


@router.post(
    "",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new position",
    description="Create a new position with the provided data"
)
async def create_position(
    position_data: PositionCreate,
    db: Client = Depends(get_db_client)
):
    """
    Create a new position.

    - **challenge_id**: ID of the challenge (optional)
    - **bet**: Bet amount (optional)
    - **side**: Side chosen - TEAM_A or TEAM_B (optional)
    - **creator**: ID of the user who created the position (optional)
    """
    service = get_position_service(db)
    try:
        return await service.create_position(position_data)
    except Exception as e:
        logger.error(f"Failed to create position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create position"
        )


@router.get(
    "",
    response_model=PositionListResponse,
    summary="List all positions",
    description="Get a paginated list of all positions"
)
async def list_positions(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of positions to return"),
    offset: int = Query(0, ge=0, description="Number of positions to skip"),
    creator: int | None = Query(None, description="Filter by creator user ID"),
    db: Client = Depends(get_db_client)
):
    """
    List all positions with pagination.

    - **limit**: Maximum number of positions to return (default: 100, max: 1000)
    - **offset**: Number of positions to skip for pagination (default: 0)
    """
    service = get_position_service(db)
    try:
        positions = await service.list_positions(limit=limit, offset=offset, creator_id=creator)
        total = await service.count_positions(creator_id=creator)
        return PositionListResponse(positions=positions, total=total)
    except Exception as e:
        logger.error(f"Failed to list positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve positions"
        )


@router.get(
    "/{position_id}",
    response_model=PositionResponse,
    summary="Get position by ID",
    description="Retrieve a specific position by its ID"
)
async def get_position(
    position_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Get a position by its ID.

    - **position_id**: The unique ID of the position
    """
    service = get_position_service(db)
    try:
        position = await service.get_position(position_id)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position with ID {position_id} not found"
            )
        return position
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get position {position_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve position"
        )


@router.get(
    "/by-challenge/{challenge_id}",
    response_model=list[PositionResponse],
    summary="Get positions by challenge",
    description="Retrieve all positions for a specific challenge"
)
async def get_positions_by_challenge(
    challenge_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Get all positions for a specific challenge.

    - **challenge_id**: The ID of the challenge
    """
    service = get_position_service(db)
    try:
        positions = await service.get_positions_by_challenge(challenge_id)
        return positions
    except Exception as e:
        logger.error(f"Failed to get positions by challenge {challenge_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve positions"
        )


@router.get(
    "/by-creator/{creator_id}",
    response_model=list[PositionResponse],
    summary="Get positions by creator",
    description="Retrieve all positions created by a specific user"
)
async def get_positions_by_creator(
    creator_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Get all positions created by a specific user.

    - **creator_id**: The ID of the user who created the positions
    """
    service = get_position_service(db)
    try:
        positions = await service.get_positions_by_creator(creator_id)
        return positions
    except Exception as e:
        logger.error(f"Failed to get positions by creator {creator_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve positions"
        )


@router.get(
    "/by-side/{side}",
    response_model=list[PositionResponse],
    summary="Get positions by side",
    description="Retrieve all positions with a specific side"
)
async def get_positions_by_side(
    side: Side,
    db: Client = Depends(get_db_client)
):
    """
    Get all positions with a specific side.

    - **side**: The side to filter by (TEAM_A or TEAM_B)
    """
    service = get_position_service(db)
    try:
        positions = await service.get_positions_by_side(side)
        return positions
    except Exception as e:
        logger.error(f"Failed to get positions by side {side}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve positions"
        )


@router.patch(
    "/{position_id}",
    response_model=PositionResponse,
    summary="Update position",
    description="Update an existing position's data"
)
async def update_position(
    position_id: int,
    position_data: PositionUpdate,
    db: Client = Depends(get_db_client)
):
    """
    Update a position by ID. Only provided fields will be updated.

    - **position_id**: The unique ID of the position to update
    - **challenge_id**: New challenge ID (optional)
    - **bet**: New bet amount (optional)
    - **side**: New side (optional)
    - **creator**: New creator ID (optional)
    """
    service = get_position_service(db)
    try:
        position = await service.update_position(position_id, position_data)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position with ID {position_id} not found"
            )
        return position
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update position {position_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update position"
        )


@router.delete(
    "/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete position",
    description="Delete a position by its ID"
)
async def delete_position(
    position_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Delete a position by its ID.

    - **position_id**: The unique ID of the position to delete
    """
    service = get_position_service(db)
    try:
        deleted = await service.delete_position(position_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position with ID {position_id} not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete position {position_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete position"
        )
