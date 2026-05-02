"""Markets API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from config import get_supabase
from models.market import (
    MarketCreate,
    MarketListResponse,
    MarketResponse,
    MarketUpdate,
)
from utils import serialize_payload

router = APIRouter(prefix="/markets", tags=["markets"])


def coerce_market(row: dict) -> MarketResponse:
    return MarketResponse.model_validate(row)


@router.post("", response_model=MarketResponse, status_code=201)
def create_market(
    market: MarketCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> MarketResponse:
    """
    Create a new market.

    Example:
        curl -X POST http://localhost:8000/markets \\
          -H "Content-Type: application/json" \\
          -d '{
            "name": "Crypto Markets",
            "slug": "crypto-markets",
            "description": "Cryptocurrency prediction markets",
            "market_type": "binary",
            "is_active": true
          }'
    """
    payload = serialize_payload(market.model_dump())

    try:
        result = (
            supabase.table("markets")
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to insert market: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to insert market")

    return coerce_market(result.data[0])


@router.get("", response_model=MarketListResponse)
def get_markets(
    supabase: Annotated[Client, Depends(get_supabase)],
    market_type: str | None = None,
    parent_id: str | None = None,
    is_active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MarketListResponse:
    """
    Get a list of markets with optional filters.

    Example:
        curl "http://localhost:8000/markets?market_type=binary&is_active=true&limit=10&offset=0"
    """
    query = supabase.table("markets").select("*")

    if market_type is not None:
        query = query.eq("market_type", market_type)
    if parent_id is not None:
        query = query.eq("parent_id", parent_id)
    if is_active is not None:
        query = query.eq("is_active", is_active)

    try:
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch markets: {exc}",
        ) from exc

    rows = result.data or []
    return MarketListResponse(
        markets=[coerce_market(row) for row in rows],
        count=len(rows),
    )


@router.get("/{market_id}", response_model=MarketResponse)
def get_market_by_id(
    market_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> MarketResponse:
    """
    Get a market by its ID.

    Example:
        curl http://localhost:8000/markets/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        result = (
            supabase.table("markets")
            .select("*")
            .eq("id", market_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch market: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Market not found")

    return coerce_market(rows[0])


@router.get("/slug/{slug}", response_model=MarketResponse)
def get_market_by_slug(
    slug: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> MarketResponse:
    """
    Get a market by its slug.

    Example:
        curl http://localhost:8000/markets/slug/crypto-markets
    """
    try:
        result = (
            supabase.table("markets")
            .select("*")
            .eq("slug", slug)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch market: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Market not found")

    return coerce_market(rows[0])


@router.patch("/{market_id}", response_model=MarketResponse)
def update_market(
    market_id: str,
    market_update: MarketUpdate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> MarketResponse:
    """
    Update a market.

    Example:
        curl -X PATCH http://localhost:8000/markets/123e4567-e89b-12d3-a456-426614174000 \\
          -H "Content-Type: application/json" \\
          -d '{"is_active": false, "total_volume": 1000}'
    """
    # First check if market exists
    try:
        existing = (
            supabase.table("markets")
            .select("*")
            .eq("id", market_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch market: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Market not found")

    # Build update payload (only non-None fields)
    update_payload = {k: v for k, v in market_update.model_dump().items() if v is not None}
    update_payload = serialize_payload(update_payload)

    if not update_payload:
        raise HTTPException(
            status_code=422,
            detail="No fields to update",
        )

    try:
        result = (
            supabase.table("markets")
            .update(update_payload)
            .eq("id", market_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update market: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update market")

    return coerce_market(result.data[0])


@router.delete("/{market_id}", status_code=204, response_model=None)
def delete_market(
    market_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    """
    Delete a market by its ID.

    Example:
        curl -X DELETE http://localhost:8000/markets/123e4567-e89b-12d3-a456-426614174000
    """
    # First check if market exists
    try:
        existing = (
            supabase.table("markets")
            .select("id")
            .eq("id", market_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch market: {exc}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Market not found")

    try:
        supabase.table("markets").delete().eq("id", market_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete market: {exc}",
        ) from exc
