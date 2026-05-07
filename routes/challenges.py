"""Challenge API endpoints."""

from enum import Enum
from typing import Annotated
 

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from config import get_supabase
from models import challenge
from models.challenge import (
    ChallengeJoin,
    ChallengeCreate,
    ChallengeListResponse,
    ChallengeResponse,
    ChallengeStatus,
    ChallengeUpdate,
    EnrichedChallengeResponse
)
from models.challenge_side import SideKey
from utils import serialize_payload
from routes.transform import transform as _transform, TransformRequest
from config import get_settings
from services.challenge_ai import validate_and_transform_statement
router = APIRouter(prefix="/challenges", tags=["challenges"])


class ChallengeSort(str, Enum):
    latest = "latest"
    expiring_soon = "expiring_soon"


def coerce_challenge(row: dict, supabase: Client) -> EnrichedChallengeResponse:
    # 1. Market Info
    market_name = row.get("category")
    market_info = None
    if market_name:
        market_res = supabase.table("markets").select("name, image, icon, description, parent_id, parent_name").eq("name", market_name).single().execute()
        market_info = market_res.data

    # 2. Creator Info
    creator_id = row.get("created_by")
    creator_info = None
    if creator_id:
        user_res = supabase.table("users").select("username, profile_image", "wallet_address").eq("id", creator_id).single().execute()
        creator_info = user_res.data

    # 3. Opponent Info
    opponent_info = None
    sides_res = supabase.table("challenge_sides").select("*").eq("challenge_id", row.get("id")).eq("side_key", SideKey.OPPONENT.value).execute()
    if sides_res.data and len(sides_res.data) > 0:
        opponent_side = sides_res.data[0]
        opponent_id = opponent_side.get("user_id")
        if opponent_id:
            user_res = supabase.table("users").select("username, profile_image", "wallet_address").eq("id", opponent_id).single().execute()
            opponent_info = user_res.data

    return EnrichedChallengeResponse(
        id=row["id"],
        title=row["title"],
        asset_name=row.get("asset_name"),
        mode=row["mode"],
        initial_bet=row["initial_bet"],
        target_price=row.get("target_price"),
        min_accept_bet=row.get("min_accept_bet"),
        max_accept_bet=row.get("max_accept_bet"),
        min_bet=row["min_bet"],
        total_pool=row["total_pool"],
        status=row["status"],
        resolution_status=row.get("resolution_status"),
        expire_time=row["expire_time"],
        resolve_time=row.get("resolve_time"),
        resolved_at=row.get("resolved_at"),
        result=row.get("result"),
        metadata=row.get("metadata"),
        created_at=row.get("created_at"),
        total_challengers=row["total_challengers"],
        total_opponents=row["total_opponents"],
        market=market_info,
        creator=creator_info,
        opponent_info=opponent_info
    )


def enrich_challenges(rows: list[dict], supabase: Client) -> list[EnrichedChallengeResponse]:
    if not rows:
        return []

    market_names = sorted({row.get("category") for row in rows if row.get("category")})
    creator_ids = sorted({row.get("created_by") for row in rows if row.get("created_by")})
    challenge_ids = [row["id"] for row in rows if row.get("id")]

    markets_map: dict[str, dict] = {}
    users_map: dict[str, dict] = {}
    participant_by_challenge: dict[str, dict] = {}

    if market_names:
        try:
            markets_res = (
                supabase.table("markets")
                .select("name, image, icon, description, parent_id, parent_name")
                .in_("name", market_names)
                .execute()
            )
            for market in markets_res.data or []:
                if market.get("name"):
                    markets_map[market["name"]] = market
        except Exception:
            markets_map = {}

    if challenge_ids:
        try:
            sides_res = (
                supabase.table("challenge_sides")
                .select("challenge_id, user_id, side_key")
                .in_("challenge_id", challenge_ids)
                .execute()
            )
            challenge_sides = sides_res.data or []
            participant_ids = sorted({side.get("user_id") for side in challenge_sides if side.get("user_id")})
        except Exception:
            challenge_sides = []
            participant_ids = []
    else:
        challenge_sides = []
        participant_ids = []

    user_ids = sorted(set(creator_ids + participant_ids))
    if user_ids:
        try:
            users_res = (
                supabase.table("users")
                .select("id, username, profile_image, wallet_address")
                .in_("id", user_ids)
                .execute()
            )
            for user in users_res.data or []:
                if user.get("id"):
                    users_map[user["id"]] = {
                        "username": user.get("username"),
                        "profile_image": user.get("profile_image"),
                        "wallet_address": user.get("wallet_address"),
                    }
        except Exception:
            users_map = {}

    for row in rows:
        challenge_id = row.get("id")
        creator_id = row.get("created_by")
        if not challenge_id:
            continue

        challenge_side_rows = [
            side for side in challenge_sides
            if side.get("challenge_id") == challenge_id and side.get("user_id")
        ]

        preferred_side = next(
            (side for side in challenge_side_rows if side.get("side_key") == SideKey.OPPONENT.value),
            None,
        )

        fallback_side = next(
            (side for side in challenge_side_rows if side.get("user_id") != creator_id),
            None,
        )

        picked_side = preferred_side or fallback_side
        picked_user_id = picked_side.get("user_id") if picked_side else None

        if challenge_id and picked_user_id and picked_user_id in users_map:
            participant_by_challenge[challenge_id] = users_map[picked_user_id]

    enriched: list[EnrichedChallengeResponse] = []
    for row in rows:
        creator_id = row.get("created_by")
        enriched.append(
            EnrichedChallengeResponse(
                id=row["id"],
                title=row["title"],
                asset_name=row.get("asset_name"),
                mode=row["mode"],
                initial_bet=row.get("initial_bet") or 0,
                target_price=row.get("target_price"),
                min_accept_bet=row.get("min_accept_bet"),
                max_accept_bet=row.get("max_accept_bet"),
                min_bet=row.get("min_bet") or 1,
                total_pool=row.get("total_pool") or 0,
                status=row.get("status") or ChallengeStatus.open.value,
                resolution_status=row.get("resolution_status"),
                expire_time=row["expire_time"],
                resolve_time=row.get("resolve_time"),
                resolved_at=row.get("resolved_at"),
                result=row.get("result"),
                metadata=row.get("metadata"),
                created_at=row.get("created_at"),
                total_challengers=row.get("total_challengers") or 0,
                total_opponents=row.get("total_opponents") or 0,
                market=markets_map.get(row.get("category")),
                creator=users_map.get(creator_id) if creator_id else None,
                opponent_info=participant_by_challenge.get(row["id"]),
            )
        )
    return enriched


@router.post("", status_code=201)
def create_challenge(
    challenge: ChallengeCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
    target_price: Annotated[int | None, Query()] = None,
) -> dict:
    """
    Create a new challenge.

    Example:
        curl -X POST http://localhost:8000/challenges \\
          -H "Content-Type: application/json" \\
          -d '{
            "title": "Will BTC reach $100k by end of 2025?",
            "description": "Binary prediction market for Bitcoin price",
            "category": "crypto",
            "asset_name": "Bitcoin",
            "event_type": "binary",
            "ticker": "BTC",
            "mode": "pool",
            "initial_bet": 10,
            "min_bet": 1,
            "bet_unit": 1,
            "expire_time": "2025-12-31T23:59:59Z",
            "resolve_time": "2026-01-01T12:00:00Z",
            "resolution_config": {}
          }'
    """

    AI_VALIDATED_CATEGORIES = {
        "ipl",
        "fifa",
    }

    if challenge.category.lower() in AI_VALIDATED_CATEGORIES:

        settings = get_settings()

        validation = validate_and_transform_statement(
            category=challenge.category,
            statement=challenge.title,
            api_key=settings.openai_api_key,
        )

        if validation["status"] != "ok":
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Invalid challenge title",
                    "status": validation["status"],
                    "suggestions": validation["statements"],
                },
            )

        # normalize title automatically
        challenge.title = validation["statements"][0]

        payload = serialize_payload({
            **challenge.model_dump(),
            "target_price": target_price if target_price is not None else challenge.target_price,
            "status": ChallengeStatus.open.value,
            "resolution_status": "pending",
            "resolution_mode": "at_time",
            "total_pool": 0,
            "total_challengers": 1,
            "total_opponents": 0,
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

    challenge_row = result.data[0]
    challenge_id = challenge_row["id"]

    # Create challenge side (challenger)
    side_payload = serialize_payload({
        "challenge_id": challenge_id,
        "user_id": challenge.created_by,
        "side_key": SideKey.CHALLENGER.value,
        "display_name": SideKey.CHALLENGER.value,
        "total_amount": challenge.initial_bet,
    })

    try:
        side_result = (
            supabase.table("challenge_sides")
            .insert(side_payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to insert challenge side: {exc}",
        ) from exc

    if not side_result.data:
        raise HTTPException(status_code=500, detail="Failed to insert challenge side")

    side_row = side_result.data[0]
    side_id = side_row["id"]

    # Create position for the challenge creator
    if challenge.created_by:
        position_payload = serialize_payload({
            "challenge_id": challenge_id,
            "side_id": side_id,
            "user_id": challenge.created_by,
            "amount": challenge.initial_bet,
        })

        try:
            (
                supabase.table("positions")
                .insert(position_payload)
                .execute()
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to insert position: {exc}",
            ) from exc

    return {"status": "ok"}


@router.get("", response_model=ChallengeListResponse)
def get_challenges(
    supabase: Annotated[Client, Depends(get_supabase)],
    status: ChallengeStatus | None = None,
    category: str | None = None,
    ticker: str | None = None,
    created_by: str | None = None,
    search: str | None = None,
    sort: Annotated[ChallengeSort, Query()] = ChallengeSort.latest,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChallengeListResponse:
    """
    Get a list of challenges with optional filters.
 
    Example:
        curl "http://localhost:8000/challenges?status=open&category=123e4567-e89b-12d3-a456-426614174000&ticker=BTC&limit=10&offset=0"
    """
    query = supabase.table("challenges").select("*", count="exact")
 
    if status is not None:
        query = query.eq("status", status.value)
    if category:
        query = query.eq("category", category)
    if ticker:
        query = query.eq("ticker", ticker)
    if created_by:
        query = query.eq("created_by", created_by)
    if search:
        query = query.ilike("title", f"%{search}%")
 
    try:
        order_column = "expire_time" if sort == ChallengeSort.expiring_soon else "created_at"
        result = (
            query.order(order_column, desc=False if sort == ChallengeSort.expiring_soon else True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenges: {exc}",
        ) from exc
 
    rows = result.data or []
    total_count = result.count if result.count is not None else len(rows)
    return ChallengeListResponse(challenges=enrich_challenges(rows, supabase), count=total_count)


@router.get("/{challenge_id}", response_model=EnrichedChallengeResponse)
def get_challenge_by_id(
    challenge_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> EnrichedChallengeResponse:
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

    return enrich_challenges(rows, supabase)[0]


@router.patch("/{challenge_id}", response_model=EnrichedChallengeResponse)
def update_challenge(
    challenge_id: str,
    challenge_update: ChallengeUpdate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> EnrichedChallengeResponse:
    """
    Update a challenge.

    Example:
        curl -X PATCH http://localhost:8000/challenges/123e4567-e89b-12d3-a456-426614174000 \\
          -H "Content-Type: application/json" \\
          -d '{"status": "resolved", "resolution_status": "resolved", "result": {"outcome": "YES"}}'
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
    update_payload = serialize_payload(update_payload)

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

    return enrich_challenges([result.data[0]], supabase)[0]


@router.delete("/{challenge_id}", status_code=204, response_model=None)
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


@router.post("/join", status_code=201)
def join_challenge(
    join_data: ChallengeJoin,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> dict:
    """
    Join a challenge by creating a side and a position.
    """
    # Fetch challenge data to update counts
    try:
        challenge_result = (
            supabase.table("challenges")
            .select("total_challengers, total_opponents")
            .eq("id", join_data.challenge_id)
            .single()
            .execute()
        )
        if not challenge_result.data:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        challenge_data = challenge_result.data
        
        # Determine which count to increment
        update_payload = {}
        if join_data.side == SideKey.CHALLENGER:
            update_payload["total_challengers"] = (challenge_data.get("total_challengers") or 0) + 1
        elif join_data.side == SideKey.OPPONENT:
            update_payload["total_opponents"] = (challenge_data.get("total_opponents") or 0) + 1
        
        if update_payload:
            supabase.table("challenges").update(serialize_payload(update_payload)).eq("id", join_data.challenge_id).execute()

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update challenge counts: {exc}",
        ) from exc

    # Check if user has already joined this challenge
    try:
        existing_position = (
            supabase.table("positions")
            .select("id")
            .eq("challenge_id", join_data.challenge_id)
            .eq("user_id", join_data.user_id)
            .execute()
        )
        if existing_position.data:
            raise HTTPException(
                status_code=400,
                detail="User has already joined this challenge"
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check existing position: {exc}",
        ) from exc

    # 1. Create challenge side
    side_payload = serialize_payload({
        "challenge_id": join_data.challenge_id,
        "user_id": join_data.user_id,
        "side_key": join_data.side.value,
        "display_name": join_data.side.value,
        "total_amount": join_data.bet_amount,
    })

    try:
        side_result = (
            supabase.table("challenge_sides")
            .insert(side_payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to insert challenge side: {exc}",
        ) from exc

    if not side_result.data:
        raise HTTPException(status_code=500, detail="Failed to insert challenge side")

    side_id = side_result.data[0]["id"]

    # 2. Create position
    position_payload = serialize_payload({
        "challenge_id": join_data.challenge_id,
        "side_id": side_id,
        "user_id": join_data.user_id,
        "amount": join_data.bet_amount,
    })

    try:
        position_result = (
            supabase.table("positions")
            .insert(position_payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to insert position: {exc}",
        ) from exc

    if not position_result.data:
        raise HTTPException(status_code=500, detail="Failed to insert position")

    return {"status": "ok"}



