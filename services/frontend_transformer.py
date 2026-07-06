"""
Transform raw DB records into shapes the RektoFun frontend expects.
The frontend was built expecting a richer / different schema than the
raw Supabase tables expose.  This layer bridges that gap so every
route can return data the UI can actually render without crashing.
"""
from typing import Any, Optional

from config import get_settings


def _first_letter_upper(val: str | None) -> str:
    return (val or "").capitalize()


def _status_to_frontend(raw_status: str | None) -> str:
    """Backend uses UPPER enums; frontend expects lower-case strings."""
    mapping = {
        "OPEN": "open",
        "PENDING_RESOLUTION": "resolving",
        "EXPIRED": "expired",
        "RESOLVED": "resolved",
        "CANCELLED": "cancelled",
    }
    return mapping.get((raw_status or "").upper(), "open")


def transform_challenge(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a raw 'challenge' DB row into the ChallengeListItem shape
    the frontend components expect.
    """
    raw_status = raw.get("status") or "OPEN"
    frontend_status = _status_to_frontend(raw_status)

    # Resolve dates
    expiry = raw.get("expiry") or ""
    resolution_date = raw.get("resolution_date") or ""
    created_at = raw.get("created_at") or ""

    # Statement is used as the title in the UI
    statement = raw.get("statement") or ""

    # Build market object
    category = raw.get("category")
    ticker = raw.get("ticker")
    market_name = category or ticker or "Unknown"

    # Get creator info from the joined user data or metadata
    creator = raw.get("creator")
    metadata = raw.get("metadata") or {}
    creator_wallet = ""
    if isinstance(metadata, dict):
        onchain = metadata.get("onchain") or {}
        creator_wallet = onchain.get("creator_wallet", "")

    return {
        "id": raw.get("id", 0),
        "title": statement,
        "description": statement,
        "category": category,
        "event_type": "",
        "ticker": ticker,
        "created_by": str(creator) if creator else "",
        "mode": (raw.get("mode") or "PVP").lower(),
        "initial_bet": raw.get("initial_bet") or 0,
        "min_accept_bet": 0,
        "max_accept_bet": 0,
        "min_bet": 0,
        "bet_unit": 0,
        "total_pool": raw.get("pool_size") or raw.get("initial_bet") or 0,
        "status": frontend_status,
        "resolution_status": "",
        "resolution_mode": (raw.get("resolution_method") or "").lower(),
        "resolution_source": raw.get("resolution_source"),
        "resolution_config": {},
        "expire_time": expiry,
        "resolve_time": resolution_date,
        "resolved_at": None,
        "result": None,
        "metadata": metadata,
        "created_at": str(created_at),
        "updated_at": str(created_at),
        "target_price": raw.get("target"),
        "total_challengers": raw.get("participants") or 1,
        "total_opponents": 0,
        "market": {
            "name": market_name,
            "image": "",
            "icon": "",
            "description": None,
            "parent_id": None,
        },
        "creator": {
            "username": f"User {creator}" if creator else "Anonymous",
            "profile_image": "",
            "wallet_address": creator_wallet,
        },
        "opponent_info": None,
    }


def transform_challenges(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [transform_challenge(r) for r in raw_rows]


def transform_user(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw 'user' DB row into the frontend User shape."""
    created_at = raw.get("created_at") or ""
    pubkey = raw.get("pubkey") or ""
    username = raw.get("username") or "Anonymous"
    
    # Generate deterministic referral code from pubkey so it's consistent across requests
    import hashlib
    referral_code = raw.get("referral_code") or ""
    if not referral_code and pubkey:
        referral_code = hashlib.sha256(pubkey.encode()).hexdigest()[:8].upper()
    
    # Parse JSONB arrays (or return empty arrays if not present)
    import json
    def _parse_jsonb(val):
        if val is None:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return []
        return []
    
    return {
        "id": str(raw.get("id", "")),
        "wallet_address": pubkey,
        "username": username,
        "description": raw.get("bio") or "",
        "profile_image": raw.get("profile_image") or "",
        "login_type": "wallet",
        "referral_code": referral_code,
        "referred_by": raw.get("referred_by") or "",
        "referrals": _parse_jsonb(raw.get("referrals")),
        "followers": _parse_jsonb(raw.get("followers")),
        "following": _parse_jsonb(raw.get("following")),
        "created_at": str(created_at),
        "updated_at": str(created_at),
        "earnings": raw.get("earnings") or 0,
    }


def transform_category(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw 'category' DB row into the frontend Market shape."""
    cat_name = raw.get("category") or "Unknown"
    created_at = raw.get("created_at") or ""
    return {
        "id": raw.get("id", 0),
        "name": cat_name,
        "symbol": cat_name.replace("/", "_").replace(" ", "_").lower(),
        "description": f"{cat_name} market",
        "image": "",
        "icon": "",
        "parent_id": raw.get("parent_category"),
        "market_type": "crypto",
        "resolution_source": None,
        "config": None,
        "total_volume": 0,
        "is_active": True,
        "created_at": str(created_at),
        "updated_at": str(created_at),
    }
