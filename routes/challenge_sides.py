"""Challenge sides API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from config import get_supabase
from models.challenge_side import (
    ChallengeSideCreate,
    ChallengeSideListResponse,
    ChallengeSideResponse,
    ChallengeSideUpdate,
)
from utils import serialize_payload

router = APIRouter(prefix="/challenge-sides", tags=["challenge_sides"])


def coerce_challenge_side(row: dict) -> ChallengeSideResponse:
    return ChallengeSideResponse.model_validate(row)


@router.post("", response_model=ChallengeSideResponse, status_code=201)
def create_challenge_side(
    side: ChallengeSideCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeSideResponse:
    """
    Create a new challenge side.

    Example:
        curl -X POST http://localhost:8000/challenge-sides \\
          -H "Content-Type: application/json" \\
          -d '{
            "challenge_id": "123e4567-e89b-12d3-a456-426614174000",
            "side_key": "yes",
            "display_name": "Yes",
            "total_amount": 0
          }'
    """
    payload = serialize_payload(side.model_dump())

    try:
        result = (
            supabase.table("challenge_sides")
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to insert challenge side: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to insert challenge side")

    return coerce_challenge_side(result.data[0])


@router.get("", response_model=ChallengeSideListResponse)
def get_challenge_sides(
    supabase: Annotated[Client, Depends(get_supabase)],
    challenge_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChallengeSideListResponse:
    """
    Get a list of challenge sides with optional filters.

    Example:
        curl "http://localhost:8000/challenge-sides?challenge_id=123e4567-e89b-12d3-a456-426614174000&limit=10&offset=0"
    """
    query = supabase.table("challenge_sides").select("*")

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
            detail=f"Failed to fetch challenge sides: {exc}",
        ) from exc

    rows = result.data or []
    return ChallengeSideListResponse(
        sides=[coerce_challenge_side(row) for row in rows],
        count=len(rows),
    )


@router.get("/{side_id}", response_model=ChallengeSideResponse)
def get_challenge_side_by_id(
    side_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeSideResponse:
    """
    Get a challenge side by its ID.

    Example:
        curl http://localhost:8000/challenge-sides/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        result = (
            supabase.table("challenge_sides")
            .select("*")
            .eq("id", side_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge side: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Challenge side not found")

    return coerce_challenge_side(rows[0])


@router.patch("/{side_id}", response_model=ChallengeSideResponse)
def update_challenge_side(
    side_id: str,
    side_update: ChallengeSideUpdate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ChallengeSideResponse:
    """
    Update a challenge side.

    Example:
        curl -X PATCH http://localhost:8000/challenge-sides/123e4567-e89b-12d3-a456-426614174000 \\
          -H "Content-Type: application/json" \\
          -d '{"display_name": "Yes Side", "total_amount": 1000}'
    """
    # First check if challenge side exists
    try:
        existing = (
            supabase.table("challenge_sides")
            .select("*")
            .eq("id", side_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge side: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Challenge side not found")

    # Build update payload (only non-None fields)
    update_payload = {k: v for k, v in side_update.model_dump().items() if v is not None}
    update_payload = serialize_payload(update_payload)

    if not update_payload:
        raise HTTPException(
            status_code=422,
            detail="No fields to update",
        )

    try:
        result = (
            supabase.table("challenge_sides")
            .update(update_payload)
            .eq("id", side_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update challenge side: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update challenge side")

    return coerce_challenge_side(result.data[0])


@router.delete("/{side_id}", status_code=204, response_model=None)
def delete_challenge_side(
    side_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    """
    Delete a challenge side by its ID.

    Example:
        curl -X DELETE http://localhost:8000/challenge-sides/123e4567-e89b-12d3-a456-426614174000
    """
    # First check if challenge side exists
    try:
        existing = (
            supabase.table("challenge_sides")
            .select("id")
            .eq("id", side_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch challenge side: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Challenge side not found")

    try:
        supabase.table("challenge_sides").delete().eq("id", side_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete challenge side: {exc}",
        ) from exc
