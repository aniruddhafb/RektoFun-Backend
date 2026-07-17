import logging

from supabase import Client

from models.notification import NotificationListResponse, NotificationResponse

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, db: Client):
        self.db = db

    async def notify_followers(self, actor_id: int, challenge_id: int, event_type: str) -> None:
        """Create one notification for every user following the actor."""
        try:
            actor_result = self.db.table("user").select("username").eq("id", actor_id).limit(1).execute()
            if not actor_result.data:
                return
            actor_name = actor_result.data[0].get("username") or "A user you follow"
            # postgrest-py 0.16 (used by supabase 2.7) joins array filter
            # values as strings. Passing an int raises TypeError before the
            # request is sent, which previously got swallowed by this method.
            followers = (
                self.db.table("user")
                .select("id")
                .contains("following", [str(actor_id)])
                .execute()
            )
            verb = "created" if event_type == "challenge_created" else "joined"
            rows = [
                {
                    "recipient_id": follower["id"],
                    "actor_id": actor_id,
                    "challenge_id": challenge_id,
                    "event_type": event_type,
                    "message": f"{actor_name} {verb} a challenge",
                    "event_key": f"{event_type}:{challenge_id}:{actor_id}:{follower['id']}",
                }
                for follower in (followers.data or [])
                if follower["id"] != actor_id
            ]
            if rows:
                self.db.table("notification").upsert(rows, on_conflict="event_key", ignore_duplicates=True).execute()
        except Exception as error:
            # A notification failure must never roll back a paid challenge action.
            logger.error("Failed to notify followers for user %s: %s", actor_id, error)

    async def notify_user_followed(
        self, actor_id: int, recipient_id: int, *, followed_back: bool = False
    ) -> None:
        """Notify a user that another user started following them."""
        try:
            actor_result = self.db.table("user").select("username").eq("id", actor_id).limit(1).execute()
            if not actor_result.data:
                return
            actor_name = actor_result.data[0].get("username") or "Someone"
            event_type = "user_followed_back" if followed_back else "user_followed"
            action = "followed you back" if followed_back else "followed you"
            row = {
                "recipient_id": recipient_id,
                "actor_id": actor_id,
                "challenge_id": None,
                "event_type": event_type,
                "message": f"{actor_name} {action}.",
                "event_key": f"{event_type}:{actor_id}:{recipient_id}",
            }
            self.db.table("notification").upsert(
                row, on_conflict="event_key", ignore_duplicates=True
            ).execute()
        except Exception as error:
            # Following should still succeed if a notification cannot be created.
            logger.error("Failed to notify user %s about follower %s: %s", recipient_id, actor_id, error)

    async def notify_pvp_winner(self, challenge: dict) -> None:
        """Notify the winner once when a contested PVP challenge is resolved."""
        try:
            if str(challenge.get("mode") or "").upper() != "PVP":
                return
            winning_side = str(challenge.get("result") or "").upper()
            if winning_side not in {"TEAM_A", "TEAM_B"}:
                return
            if winning_side == "TEAM_A":
                winner_id = challenge.get("creator")
            else:
                winner_id = (
                    ((challenge.get("bet_info") or {}).get("highest_bet") or {})
                    .get("TEAM_B", {})
                    .get("id")
                )
            if not winner_id:
                return
            winner = self.db.table("user").select("id,username").eq("id", winner_id).limit(1).execute()
            if not winner.data:
                return
            team_count = (challenge.get("bet_info") or {}).get("team_count") or {}
            recorded_pool = sum(
                float((team_count.get(side) or {}).get("total_amount") or 0)
                for side in ("TEAM_A", "TEAM_B")
            )
            amount = float(recorded_pool or challenge.get("total_pool") or challenge.get("pool_size") or challenge.get("initial_bet") or 0)
            amount_label = f"{amount:,.2f}".rstrip("0").rstrip(".")
            row = {
                "recipient_id": winner_id,
                "actor_id": winner_id,
                "challenge_id": challenge.get("id"),
                "event_type": "challenge_won",
                "message": f"You won {amount_label} USDC in a PVP challenge!",
                "event_key": f"challenge_won:{challenge.get('id')}:{winner_id}",
            }
            self.db.table("notification").upsert(
                row, on_conflict="event_key", ignore_duplicates=True
            ).execute()
        except Exception as error:
            logger.error("Failed to notify winner for challenge %s: %s", challenge.get("id"), error)

    async def list_for_wallet(self, wallet: str, limit: int = 50) -> NotificationListResponse:
        user_result = self.db.table("user").select("id").eq("pubkey", wallet).limit(1).execute()
        if not user_result.data:
            raise ValueError("User not found")
        recipient_id = user_result.data[0]["id"]
        result = (
            self.db.table("notification")
            .select("*, actor:user!notification_actor_id_fkey(username, profile_image, pubkey)")
            .eq("recipient_id", recipient_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        notifications = []
        for row in result.data or []:
            actor = row.pop("actor", None) or {}
            notifications.append(NotificationResponse(
                **row,
                actor_username=actor.get("username"),
                actor_profile_image=actor.get("profile_image"),
                actor_wallet_address=actor.get("pubkey"),
            ))
        unread = sum(1 for item in notifications if not item.is_read)
        return NotificationListResponse(notifications=notifications, unread_count=unread)

    async def mark_read(self, wallet: str, notification_id: int | None = None) -> None:
        user_result = self.db.table("user").select("id").eq("pubkey", wallet).limit(1).execute()
        if not user_result.data:
            raise ValueError("User not found")
        query = self.db.table("notification").update({"is_read": True}).eq("recipient_id", user_result.data[0]["id"])
        if notification_id is not None:
            query = query.eq("id", notification_id)
        query.execute()


def get_notification_service(db: Client) -> NotificationService:
    return NotificationService(db)
