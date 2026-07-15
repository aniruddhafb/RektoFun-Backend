import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from services.database import get_db_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activity", tags=["activity"])


def _timestamp(value: str | None) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


@router.get("", summary="Get the paginated live activity feed")
async def list_activity(
    limit: int = Query(15, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Client = Depends(get_db_client),
):
    """Build a small feed page server-side instead of downloading whole tables."""
    try:
        candidate_count = offset + limit + 1
        challenges_result = (
            db.table("challenge")
            .select("*, creator_details:user!challenge_creator_fkey(*)")
            .order("created_at", desc=True)
            .limit(candidate_count)
            .execute()
        )
        positions_result = (
            db.table("position")
            .select("*")
            .order("created_at", desc=True)
            .limit(candidate_count)
            .execute()
        )

        challenges = list(challenges_result.data or [])
        positions = list(positions_result.data or [])
        challenge_ids = {position.get("challenge_id") for position in positions if position.get("challenge_id")}
        known_ids = {challenge.get("id") for challenge in challenges}
        missing_ids = list(challenge_ids - known_ids)
        if missing_ids:
            related = (
                db.table("challenge")
                .select("*, creator_details:user!challenge_creator_fkey(*)")
                .in_("id", missing_ids)
                .execute()
            )
            challenges.extend(related.data or [])

        user_ids = {position.get("creator") for position in positions if position.get("creator")}
        users = {}
        if user_ids:
            user_result = db.table("user").select("*").in_("id", list(user_ids)).execute()
            users = {user["id"]: user for user in (user_result.data or [])}

        challenge_by_id = {challenge["id"]: challenge for challenge in challenges}
        events = []
        for challenge in challenges_result.data or []:
            actor = challenge.get("creator_details")
            events.append({
                "id": f"created-{challenge['id']}",
                "type": "created",
                "occurredAt": challenge.get("created_at"),
                "challenge": challenge,
                "actor": actor,
            })

            challenge_status = str(challenge.get("status") or "").lower()
            if challenge_status == "cancelled":
                occurred_at = challenge.get("cancelled_at") or challenge.get("updated_at") or challenge.get("created_at")
                events.append({
                    "id": f"cancelled-{challenge['id']}", "type": "cancelled",
                    "occurredAt": occurred_at, "challenge": challenge, "actor": actor,
                })

        joined_challenge_ids = set()
        for position in positions:
            challenge = challenge_by_id.get(position.get("challenge_id"))
            if not challenge or position.get("creator") == challenge.get("creator"):
                continue
            joined_challenge_ids.add(challenge["id"])
            events.append({
                "id": f"joined-{position['id']}",
                "type": "joined",
                "occurredAt": position.get("created_at"),
                "challenge": challenge,
                "actor": users.get(position.get("creator")),
                "position": position,
            })

        now = datetime.now(timezone.utc).timestamp()
        for challenge in challenges_result.data or []:
            expiry = challenge.get("expire_time") or challenge.get("expiry")
            challenge_status = str(challenge.get("status") or "").lower()
            if challenge_status == "expired" or (
                expiry and _timestamp(expiry) <= now and challenge["id"] not in joined_challenge_ids
                and challenge_status not in {"resolved", "cancelled"}
            ):
                events.append({
                    "id": f"expired-{challenge['id']}", "type": "expired",
                    "occurredAt": expiry or challenge.get("created_at"),
                    "challenge": challenge, "actor": challenge.get("creator_details"),
                })

        events.sort(key=lambda event: _timestamp(event.get("occurredAt")), reverse=True)
        page = events[offset:offset + limit]
        return {"activities": page, "has_more": len(events) > offset + limit}
    except Exception as exc:
        logger.error("Failed to build activity feed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activity",
        ) from exc
