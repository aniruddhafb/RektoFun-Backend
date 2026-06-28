"""
Market API routes — bridges the backend category table to the frontend market model.
"""
import logging

from fastapi import APIRouter, HTTPException, Query, status

from config import get_settings
from services.database import get_db_client
from services.category_service import CategoryService
from services.frontend_transformer import transform_category

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", summary="List markets")
async def list_markets(
    market_type: str | None = Query(None, description="Filter by market type"),
    parent_id: str | None = Query(None, description="Filter by parent category name"),
    parent_name: str | None = Query(None, description="Filter by parent category name"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    List markets (frontend-facing wrapper over categories).
    """
    db = get_db_client()
    service = CategoryService(db)
    try:
        cats = service.get_all_categories()
        # Transform categories → markets
        markets = [transform_category(c) for c in cats]

        # Apply filters
        if parent_id == "null":
            # Frontend sends parent_id="null" to request top-level markets
            markets = [m for m in markets if m.get("parent_id") is None]
        elif parent_id or parent_name:
            parent = parent_name or parent_id
            markets = [m for m in markets if m.get("parent_id") == parent]

        if is_active is not None:
            markets = [m for m in markets if m.get("is_active") == is_active]

        total = len(markets)
        # Pagination
        markets = markets[offset : offset + limit]

        return {"markets": markets, "count": total}
    except Exception as e:
        logger.error(f"Failed to list markets: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve markets")


@router.post("", summary="Create a market")
async def create_market(payload: dict):
    """Stub: create a market. Maps to category creation internally."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Market creation via this endpoint is not implemented. Use /api/categories instead.")
