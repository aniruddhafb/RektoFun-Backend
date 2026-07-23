"""Compact, bounded data source for the navbar search modal."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from services.challenge_service import get_challenge_service
from services.database import get_request_db_client as get_db_client
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])

SEARCH_CHALLENGE_FIELDS = (
    "id,statement,ticker,trading_pair,status,bet_info,participants,pool_size,initial_bet,"
    "resolution_method,resolution_source,mode,expiry,resolution_date,created_at,category,"
    "resolves_at:metadata->composer->>resolves_at,"
    "category_image:metadata->composer->>category_image,"
    "image_url:metadata->composer->>image_url,"
    "creator_details:user!challenge_creator_fkey(username,pubkey)"
)


def _safe_search_term(value: str) -> str:
    return " ".join(value.strip().replace(",", " ").replace("(", " ").replace(")", " ").split())


def _compact_challenge(row: dict) -> dict:
    resolves_at = row.pop("resolves_at", None)
    category_image = row.pop("category_image", None) or row.pop("image_url", None)
    row["metadata"] = {"composer": {"resolves_at": resolves_at}} if resolves_at else {}
    row["category_image"] = category_image
    return row


def _compact_user(row: dict, metrics: dict | None = None) -> dict:
    compact = {
        key: row.get(key)
        for key in (
            "id", "username", "pubkey", "profile_image",
            "twitter_profile_image", "bio", "twitter_username",
            "user_type",
        )
    }
    compact["follower_count"] = len(row.get("followers") or [])
    compact["won"] = (metrics or {}).get("won") or 0
    compact["pnl"] = (metrics or {}).get("pnl") or 0
    return compact


@router.get("")
async def search_modal(
    q: str | None = Query(None, max_length=100),
    db: Client = Depends(get_db_client),
):
    """Return no more than six card-ready challenges and users."""
    try:
        term = _safe_search_term(q or "")
        challenge_query = db.table("challenge").select(SEARCH_CHALLENGE_FIELDS)
        if get_challenge_service(db).has_visibility_columns():
            challenge_query = challenge_query.eq("visibility", "PUBLIC")
        if term:
            challenge_query = challenge_query.or_(
                f"statement.ilike.%{term}%,ticker.ilike.%{term}%,trading_pair.ilike.%{term}%"
            )
        challenge_result = challenge_query.order("created_at", desc=True).limit(6).execute()

        user_query = db.table("user").select(
            "id,username,pubkey,profile_image,twitter_profile_image,bio,"
            "twitter_username,user_type,followers"
        )
        if term:
            user_query = user_query.or_(
                f"username.ilike.%{term}%,pubkey.ilike.%{term}%,twitter_username.ilike.%{term}%"
            )
        # Bound the candidate set before sorting. The modal only renders six
        # users; downloading the complete user table made every open/search slow.
        user_result = user_query.order("id", desc=True).limit(24).execute()
        users = sorted(
            user_result.data or [],
            key=lambda user: (len(user.get("followers") or []), user.get("id") or 0),
            reverse=True,
        )[:6]
        metrics_by_id = {}
        try:
            # One bounded database aggregation restores performance stats
            # without invoking LeaderboardService's full ranking, pagination,
            # role enrichment, and challenge-count scan.
            metrics_result = db.rpc("get_challenge_leaderboard", {
                "p_period": "all",
                "p_limit": 100,
                "p_offset": 0,
                "p_search": term or None,
                "p_sort": "pnl",
                "p_order": "desc",
            }).execute().data
            metric_rows = metrics_result.get("users", []) if isinstance(metrics_result, dict) else []
            metrics_by_id = {
                str(row.get("id")): row
                for row in metric_rows
                if isinstance(row, dict) and row.get("id") is not None
            }
        except Exception:
            logger.exception("Failed to load bounded search user metrics")
        # Search cards already select their artwork from compact metadata.
        # Avoid full leaderboard aggregation and category/profile enrichment in
        # this latency-sensitive endpoint.
        challenges = [_compact_challenge(row) for row in (challenge_result.data or [])]
        return {
            "challenges": challenges,
            "users": [_compact_user(row, metrics_by_id.get(str(row.get("id")))) for row in users],
        }
    except Exception as exc:
        logger.error("Failed to load compact search results: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load search results") from exc
