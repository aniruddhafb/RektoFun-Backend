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

    async def list_for_wallet(self, wallet: str, limit: int = 50) -> NotificationListResponse:
        user_result = self.db.table("user").select("id").eq("pubkey", wallet).limit(1).execute()
        if not user_result.data:
            raise ValueError("User not found")
        recipient_id = user_result.data[0]["id"]
        result = (
            self.db.table("notification")
            .select("*, actor:user!notification_actor_id_fkey(username, profile_image)")
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
