"""Positions API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from config import get_supabase
from models.position import (
    PositionCreate,
    PositionListResponse,
    PositionResponse,
    PositionUpdate,
)
from utils import serialize_payload

router = APIRouter(prefix="/positions", tags=["positions"])


def coerce_position(row: dict) -> PositionResponse:
    return PositionResponse.model_validate(row)


@router.post("", response_model=PositionResponse, status_code=201)
def create_position(
    position: PositionCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> PositionResponse:
    """
    Create a new position.

    Example:
        curl -X POST http://localhost:8000/positions \\
          -H "Content-Type: application/json" \\
          -d '{
            "challenge_id": "123e4567-e89b-12d3-a456-426614174000",
            "side_id": "456e4567-e89b-12d3-a456-426614174001",
            "user_id": "wallet_address_here",
            "amount": 100
          }'
    """
    payload = serialize_payload(position.model_dump())

    try:
        result = (
            supabase.table("positions")
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to insert position: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to insert position")

    return coerce_position(result.data[0])


@router.get("", response_model=PositionListResponse)
def get_positions(
    supabase: Annotated[Client, Depends(get_supabase)],
    challenge_id: str | None = None,
    side_id: str | None = None,
    user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PositionListResponse:
    """
    Get a list of positions with optional filters.

    Example:
        curl "http://localhost:8000/positions?challenge_id=123e4567-e89b-12d3-a456-426614174000&user_id=wallet_address&limit=10&offset=0"
    """
    query = supabase.table("positions").select("*")

    if challenge_id:
        query = query.eq("challenge_id", challenge_id)
    if side_id:
        query = query.eq("side_id", side_id)
    if user_id:
        query = query.eq("user_id", user_id)

    try:
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch positions: {exc}",
        ) from exc

    rows = result.data or []
    return PositionListResponse(
        positions=[coerce_position(row) for row in rows],
        count=len(rows),
    )


@router.get("/{position_id}", response_model=PositionResponse)
def get_position_by_id(
    position_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> PositionResponse:
    """
    Get a position by its ID.

    Example:
        curl http://localhost:8000/positions/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        result = (
            supabase.table("positions")
            .select("*")
            .eq("id", position_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch position: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Position not found")

    return coerce_position(rows[0])


@router.patch("/{position_id}", response_model=PositionResponse)
def update_position(
    position_id: str,
    position_update: PositionUpdate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> PositionResponse:
    """
    Update a position.

    Example:
        curl -X PATCH http://localhost:8000/positions/123e4567-e89b-12d3-a456-426614174000 \\
          -H "Content-Type: application/json" \\
          -d '{"amount": 200}'
    """
    # First check if position exists
    try:
        existing = (
            supabase.table("positions")
            .select("*")
            .eq("id", position_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch position: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Position not found")

    # Build update payload (only non-None fields)
    update_payload = {k: v for k, v in position_update.model_dump().items() if v is not None}
    update_payload = serialize_payload(update_payload)

    if not update_payload:
        raise HTTPException(
            status_code=422,
            detail="No fields to update",
        )

    try:
        result = (
            supabase.table("positions")
            .update(update_payload)
            .eq("id", position_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update position: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update position")

    return coerce_position(result.data[0])


@router.delete("/{position_id}", status_code=204, response_model=None)
def delete_position(
    position_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    """
    Delete a position by its ID.

    Example:
        curl -X DELETE http://localhost:8000/positions/123e4567-e89b-12d3-a456-426614174000
    """
    # First check if position exists
    try:
        existing = (
            supabase.table("positions")
            .select("id")
            .eq("id", position_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch position: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Position not found")

    try:
        supabase.table("positions").delete().eq("id", position_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete position: {exc}",
        ) from exc
