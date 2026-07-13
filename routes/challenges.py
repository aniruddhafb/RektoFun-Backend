"""
Challenge API routes for CRUD operations.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from supabase import Client

from models.challenge import (
    ChallengeCreate,
    ChallengeUpdate,
    ChallengeResponse,
    ChallengeListResponse,
    ChallengeStatus,
    Direction
)
from models.position import PositionCreate, Side
from services.database import get_db_client
from services.challenge_service import get_challenge_service, ChallengeService
from services.position_service import get_position_service
from services.challenge_monitor_service import (
    monitor_new_challenge,
    stop_monitoring_challenge,
    get_challenge_monitor
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/challenges", tags=["challenges"])


async def verify_cron_api_key(x_api_key: str = Header(..., description="API key for cron job authentication")):
    """
    Dependency to verify the cron job API key.
    """
    expected_key = os.getenv("CRON_API_KEY")
    if not expected_key:
        logger.error("CRON_API_KEY environment variable not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error"
        )
    if x_api_key != expected_key:
        logger.warning(f"Invalid API key provided for cron endpoint")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )


@router.post(
    "",
    response_model=ChallengeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new challenge",
    description="Create a new challenge with the provided data"
)
async def create_challenge(
    challenge_data: ChallengeCreate,
    db: Client = Depends(get_db_client)
):
    """
    Create a new challenge.
    
    - **statement**: The challenge statement/question (optional)
    - **ticker**: The ticker symbol for the challenge (optional)
    - **target**: Target value for price-based challenges (optional)
    - **initial_bet**: Initial bet amount (optional)
    - **pool_size**: Total pool size (optional)
    - **resolution_source**: Source for resolving the challenge (optional)
    - **metadata**: Additional metadata as JSON (optional)
    - **creator**: ID of the user who created the challenge (optional)
    - **resolution_method**: Method for resolving the challenge (optional)
    - **participants**: Number of participants (optional)
    - **status**: Challenge status (default: OPEN)
    - **mode**: Challenge mode - PVP or TEAM (optional)
    - **result**: Result side if resolved (optional)
    - **direction**: Direction of the challenge - UP or DOWN (optional)
    - **expiry**: Expiry timestamp for the challenge in ISO 8601 format (optional)
    - **resolution_date**: Date when the challenge will be resolved in YYYY-MM-DD format (optional)
    - **category**: Category of the challenge (optional)
    """
    service = get_challenge_service(db)
    position_service = get_position_service(db)
    try:
        # Create the challenge first
        challenge = await service.create_challenge(challenge_data)
        print("challenge", challenge)
        
        # Create a position for the challenge creator
        position_data = PositionCreate(
            challenge_id=challenge.id,
            bet=challenge.initial_bet,
            side=Side.TEAM_A,
            creator=challenge.creator
        )
        created_position = await position_service.create_position(position_data)
        print("created_position", created_position)
        # Start monitoring the challenge for price targets
        # Only monitor if it has a ticker and target price
        if challenge.ticker and challenge.target:
            challenge_dict = challenge.model_dump()
            await monitor_new_challenge(challenge_dict)
            logger.info(f"Started monitoring challenge {challenge.id} for price target")
            
        
        return challenge
    except Exception as e:
        logger.error(f"Failed to create challenge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create challenge"
        )


@router.get(
    "",
    response_model=ChallengeListResponse,
    summary="List all challenges",
    description="Get a paginated list of all challenges"
)
async def list_challenges(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of challenges to return"),
    offset: int = Query(0, ge=0, description="Number of challenges to skip"),
    db: Client = Depends(get_db_client)
):
    """
    List all challenges with pagination.
    
    - **limit**: Maximum number of challenges to return (default: 100, max: 1000)
    - **offset**: Number of challenges to skip for pagination (default: 0)
    """
    service = get_challenge_service(db)
    try:
        challenges = await service.list_challenges(limit=limit, offset=offset)
        total = await service.count_challenges()
        return ChallengeListResponse(challenges=challenges, total=total)
    except Exception as e:
        logger.error(f"Failed to list challenges: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve challenges"
        )


@router.get(
    "/monitor/active-streams",
    summary="Get active subscribed streams",
    description="Retrieve all currently active subscribed streams (trading pairs) being monitored via WebSocket"
)
async def get_active_subscribed_streams():
    """
    Get all active subscribed streams being monitored by the Challenge Monitor Service.
    
    Returns a list of active challenges with their trading pairs and monitoring details.
    """
    try:
        monitor = get_challenge_monitor()
        active_challenges = monitor.get_active_challenges()
        
        # Extract unique subscribed streams (trading pairs)
        # trading_pair holds the normalized Binance symbol (e.g. "BTCUSDC")
        # raw_trading_pair holds the original value from DB (e.g. "BTC/USDC")
        subscribed_streams = {}
        for challenge in active_challenges:
            symbol = challenge.get("trading_pair")  # normalized Binance symbol
            raw_pair = challenge.get("raw_trading_pair")  # original DB value
            if symbol:
                if symbol not in subscribed_streams:
                    subscribed_streams[symbol] = {
                        "symbol": symbol,
                        "trading_pair": raw_pair,
                        "ticker": challenge.get("ticker"),
                        "challenges": []
                    }
                subscribed_streams[symbol]["challenges"].append({
                    "challenge_id": challenge.get("challenge_id"),
                    "target": challenge.get("target"),
                    "direction": challenge.get("direction"),
                    "created_at": challenge.get("created_at")
                })

        return {
            "total_streams": len(subscribed_streams),
            "total_monitored_challenges": len(active_challenges),
            "streams": list(subscribed_streams.values())
        }
    except Exception as e:
        logger.error(f"Failed to get active subscribed streams: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active subscribed streams"
        )


@router.get(
    "/by-creator/{creator_id}",
    response_model=list[ChallengeResponse],
    summary="Get challenges by creator",
    description="Retrieve all challenges created by a specific user"
)
async def get_challenges_by_creator(
    creator_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Get all challenges created by a specific user.
    
    - **creator_id**: The ID of the user who created the challenges
    """
    service = get_challenge_service(db)
    try:
        challenges = await service.get_challenges_by_creator(creator_id)
        return challenges
    except Exception as e:
        logger.error(f"Failed to get challenges by creator {creator_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve challenges"
        )


@router.get(
    "/{challenge_id}",
    response_model=ChallengeResponse,
    summary="Get challenge by ID",
    description="Retrieve a specific challenge by its ID"
)
async def get_challenge(
    challenge_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Get a challenge by its ID.
    
    - **challenge_id**: The unique ID of the challenge
    """
    service = get_challenge_service(db)
    try:
        challenge = await service.get_challenge(challenge_id)
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Challenge with ID {challenge_id} not found"
            )
        return challenge
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get challenge {challenge_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve challenge"
        )


@router.get(
    "/by-status/{status}",
    response_model=list[ChallengeResponse],
    summary="Get challenges by status",
    description="Retrieve all challenges with a specific status"
)
async def get_challenges_by_status(
    status: ChallengeStatus,
    db: Client = Depends(get_db_client)
):
    """
    Get all challenges with a specific status.
    
    - **status**: The status to filter by (OPEN, PENDING_RESOLUTION, EXPIRED, RESOLVED, CANCELLED)
    """
    service = get_challenge_service(db)
    try:
        challenges = await service.get_challenges_by_status(status)
        return challenges
    except Exception as e:
        logger.error(f"Failed to get challenges by status {status}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve challenges"
        )


@router.get(
    "/by-category/{category}",
    response_model=list[ChallengeResponse],
    summary="Get challenges by category",
    description="Retrieve all challenges belonging to a specific category"
)
async def get_challenges_by_category(
    category: str,
    db: Client = Depends(get_db_client)
):
    """
    Get all challenges belonging to a specific category.

    - **category**: The category name to filter by
    """
    service = get_challenge_service(db)
    try:
        challenges = await service.get_challenges_by_category(category)
        return challenges
    except Exception as e:
        logger.error(f"Failed to get challenges by category {category}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve challenges"
        )


@router.patch(
    "/{challenge_id}",
    response_model=ChallengeResponse,
    summary="Update challenge",
    description="Update an existing challenge's data"
)
async def update_challenge(
    challenge_id: int,
    challenge_data: ChallengeUpdate,
    db: Client = Depends(get_db_client)
):
    """
    Update a challenge by ID. Only provided fields will be updated.
    
    - **challenge_id**: The unique ID of the challenge to update
    - **statement**: New challenge statement (optional)
    - **ticker**: New ticker symbol for the challenge (optional)
    - **target**: New target value for price-based challenges (optional)
    - **initial_bet**: New initial bet amount (optional)
    - **pool_size**: New pool size (optional)
    - **resolution_source**: New resolution source (optional)
    - **metadata**: New metadata (optional)
    - **creator**: New creator ID (optional)
    - **resolution_method**: New resolution method (optional)
    - **participants**: New participant count (optional)
    - **status**: New status (optional)
    - **mode**: New mode (optional)
    - **result**: New result (optional)
    - **direction**: New direction - UP or DOWN (optional)
    - **expiry**: New expiry timestamp in ISO 8601 format (optional)
    - **resolution_date**: New resolution date in YYYY-MM-DD format (optional)
    - **category**: New category (optional)
    """
    service = get_challenge_service(db)
    try:
        challenge = await service.update_challenge(challenge_id, challenge_data)
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Challenge with ID {challenge_id} not found"
            )
        return challenge
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update challenge {challenge_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update challenge"
        )


@router.delete(
    "/{challenge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete challenge",
    description="Delete a challenge by its ID"
)
async def delete_challenge(
    challenge_id: int,
    db: Client = Depends(get_db_client)
):
    """
    Delete a challenge by its ID.
    
    - **challenge_id**: The unique ID of the challenge to delete
    """
    service = get_challenge_service(db)
    try:
        # Stop monitoring before deleting
        await stop_monitoring_challenge(challenge_id)
        
        deleted = await service.delete_challenge(challenge_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Challenge with ID {challenge_id} not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete challenge {challenge_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete challenge"
        )


@router.post(
    "/resolve-due",
    summary="Resolve challenges by date",
    description="Resolve all OPEN challenges where resolution_date has been reached. Should be called by pg_cron daily."
)
async def resolve_challenges_due():
    """
    Resolve all OPEN challenges where resolution_date has been reached.
    
    This endpoint should be called daily (e.g., via pg_cron) to resolve challenges
    that have reached their resolution date. It fetches current prices and updates
    challenge statuses to RESOLVED.
    
    Returns the number of challenges processed.
    """
    try:
        monitor = get_challenge_monitor()
        await monitor.resolve_challenges_by_date()
        
        # Get the count of challenges that were ready for resolution
        # by checking active challenges before resolution
        active_challenges = monitor.get_active_challenges()
        
        return {
            "status": "success",
            "message": "Challenges due for resolution have been processed",
            "remaining_active_challenges": len(active_challenges)
        }
    except Exception as e:
        logger.error(f"Failed to resolve challenges by date: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve challenges"
        )


@router.post(
    "/cron/resolve-due",
    summary="Resolve challenges by date (authenticated)",
    description="Authenticated endpoint to resolve all OPEN challenges where resolution_date has been reached. Called by pg_cron daily.",
    dependencies=[Depends(verify_cron_api_key)]
)
async def resolve_challenges_due_cron():
    """
    Authenticated endpoint to resolve all OPEN challenges where resolution_date has been reached.
    
    This endpoint requires a valid CRON_API_KEY header and should be called daily
    by pg_cron to resolve challenges that have reached their resolution date.
    
    Returns the number of challenges processed.
    """
    try:
        monitor = get_challenge_monitor()
        await monitor.resolve_challenges_by_date()
        
        # Get the count of challenges that were ready for resolution
        active_challenges = monitor.get_active_challenges()
        
        return {
            "status": "success",
            "message": "Challenges due for resolution have been processed",
            "remaining_active_challenges": len(active_challenges)
        }
    except Exception as e:
        logger.error(f"Failed to resolve challenges by date: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve challenges"
        )
