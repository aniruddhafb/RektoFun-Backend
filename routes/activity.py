import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from services.database import get_request_db_client as get_db_client
from services.challenge_service import get_challenge_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activity", tags=["activity"])

ACTIVITY_CHALLENGE_FIELDS = (
    "id,statement,ticker,initial_bet,pool_size,resolution_source,creator,category,"
    "participants,status,mode,result,expiry,resolution_date,resolved_at,created_at,bet_info,"
    "metadata"
)
ACTIVITY_POSITION_FIELDS = "id,challenge_id,creator,created_at"
ACTIVITY_USER_FIELDS = "id,username,pubkey,profile_image"


def _timestamp(value: str | None) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def _compact_challenge(row: dict) -> dict:
    """Normalize nullable JSON metadata."""
    row["metadata"] = row.get("metadata") or {}
    return row


@router.get("", summary="Get the paginated live activity feed")
async def list_activity(
    limit: int = Query(15, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user_id: int | None = Query(None, ge=1),
    db: Client = Depends(get_db_client),
):
    """Build a small feed page server-side instead of downloading whole tables."""
    try:
        candidate_count = offset + limit + 1
        challenges_query = db.table("challenge").select(ACTIVITY_CHALLENGE_FIELDS)
        positions_query = db.table("position").select(ACTIVITY_POSITION_FIELDS)
        if user_id is not None:
            challenges_query = challenges_query.eq("creator", user_id)
            positions_query = positions_query.eq("creator", user_id)
        challenges_result = challenges_query.order("created_at", desc=True).limit(candidate_count).execute()
        positions_result = positions_query.order("created_at", desc=True).limit(candidate_count).execute()

        challenges = [_compact_challenge(row) for row in (challenges_result.data or [])]
        positions = list(positions_result.data or [])
        challenge_ids = {position.get("challenge_id") for position in positions if position.get("challenge_id")}
        known_ids = {challenge.get("id") for challenge in challenges}
        missing_ids = list(challenge_ids - known_ids)
        if missing_ids:
            related = (
                db.table("challenge")
                .select(ACTIVITY_CHALLENGE_FIELDS)
                .in_("id", missing_ids)
                .execute()
            )
            challenges.extend(_compact_challenge(row) for row in (related.data or []))

        # Resolve artwork once for the whole feed page using the same category
        # hierarchy/fallback logic as challenge cards.
        challenges = get_challenge_service(db).with_category_images(challenges)

        user_ids = {
            user_id
            for user_id in (
                *(position.get("creator") for position in positions),
                *(challenge.get("creator") for challenge in challenges),
            )
            if user_id
        }
        for challenge in challenges:
            if str(challenge.get("status") or "").upper() == "RESOLVED" and str(challenge.get("mode") or "").upper() == "PVP":
                winning_side = str(challenge.get("result") or "").upper()
                winner_id = challenge.get("creator") if winning_side == "TEAM_A" else (
                    (((challenge.get("bet_info") or {}).get("highest_bet") or {}).get("TEAM_B") or {}).get("id")
                )
                if winner_id:
                    user_ids.add(winner_id)
            for event in (challenge.get("metadata") or {}).get("activity_events", []):
                if isinstance(event, dict) and event.get("user_id"):
                    user_ids.add(event["user_id"])
        users = {}
        if user_ids:
            user_result = db.table("user").select(ACTIVITY_USER_FIELDS).in_("id", list(user_ids)).execute()
            users = {user["id"]: user for user in (user_result.data or [])}

        challenge_by_id = {challenge["id"]: challenge for challenge in challenges}
        events = []
        for challenge in challenges[:len(challenges_result.data or [])]:
            actor = users.get(challenge.get("creator"))
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

        # Related challenges fetched for a user's positions must also contribute
        # that user's payout/refund events, without creating duplicate lifecycle events.
        for challenge in challenges:
            if str(challenge.get("status") or "").lower() == "resolved" and str(challenge.get("mode") or "").upper() == "PVP":
                winning_side = str(challenge.get("result") or "").upper()
                winner_id = challenge.get("creator") if winning_side == "TEAM_A" else (
                    (((challenge.get("bet_info") or {}).get("highest_bet") or {}).get("TEAM_B") or {}).get("id")
                )
                if winner_id:
                    team_count = (challenge.get("bet_info") or {}).get("team_count") or {}
                    recorded_pool = sum(
                        float((team_count.get(side) or {}).get("total_amount") or 0)
                        for side in ("TEAM_A", "TEAM_B")
                    )
                    events.append({
                        "id": f"won-{challenge['id']}", "type": "won",
                        "occurredAt": challenge.get("resolved_at") or challenge.get("created_at"),
                        "amount": recorded_pool or challenge.get("pool_size") or challenge.get("initial_bet") or 0,
                        "challenge": challenge, "actor": users.get(winner_id),
                    })
            for history in (challenge.get("metadata") or {}).get("activity_events", []):
                if not isinstance(history, dict) or history.get("type") not in {"redeemed", "refunded"}:
                    continue
                actor_id = history.get("user_id")
                events.append({
                    "id": f"{history['type']}-{history.get('id') or challenge['id']}",
                    "type": history["type"],
                    "occurredAt": history.get("occurred_at") or challenge.get("created_at"),
                    "amount": history.get("amount"),
                    "challenge": challenge,
                    "actor": users.get(actor_id),
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
            })

        now = datetime.now(timezone.utc).timestamp()
        for challenge in challenges[:len(challenges_result.data or [])]:
            expiry = challenge.get("expire_time") or challenge.get("expiry")
            challenge_status = str(challenge.get("status") or "").lower()
            if challenge_status == "expired" or (
                expiry and _timestamp(expiry) <= now and challenge["id"] not in joined_challenge_ids
                and challenge_status not in {"resolved", "cancelled"}
            ):
                events.append({
                    "id": f"expired-{challenge['id']}", "type": "expired",
                    "occurredAt": expiry or challenge.get("created_at"),
                    "challenge": challenge, "actor": users.get(challenge.get("creator")),
                })

        events.sort(key=lambda event: _timestamp(event.get("occurredAt")), reverse=True)
        if user_id is not None:
            events = [
                event for event in events
                if isinstance(event.get("actor"), dict) and event["actor"].get("id") == user_id
            ]
        page = events[offset:offset + limit]
        return {"activities": page, "has_more": len(events) > offset + limit}
    except Exception as exc:
        logger.error("Failed to build activity feed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activity",
        ) from exc
