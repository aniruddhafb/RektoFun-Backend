"""Database-side leaderboard queries designed for large user populations."""

import logging
from typing import Any

from supabase import Client


logger = logging.getLogger(__name__)


class LeaderboardService:
    def __init__(self, db: Client):
        self.db = db

    async def get_leaderboard(
        self, *, period: str, limit: int, offset: int, search: str | None,
        sort: str, order: str,
    ) -> dict[str, Any]:
        """Delegate aggregation, ranking and pagination to PostgreSQL."""
        response = self.db.rpc("get_challenge_leaderboard", {
            "p_period": period,
            "p_limit": limit,
            "p_offset": offset,
            "p_search": search,
            "p_sort": sort,
            "p_order": order,
        }).execute()
        data = response.data
        if not isinstance(data, dict):
            raise RuntimeError("Leaderboard database function returned an invalid response")

        # The leaderboard RPC predates user roles, so enrich its rows with the
        # current role to let clients distinguish KOL/moderator verification.
        users = data.get("users")
        if isinstance(users, list):
            user_ids = [user.get("id") for user in users if isinstance(user, dict) and user.get("id") is not None]
            if user_ids:
                try:
                    role_response = (
                        self.db.table("users")
                        .select("id,user_type")
                        .in_("id", user_ids)
                        .execute()
                    )
                    roles = {
                        str(user["id"]): user.get("user_type", "user")
                        for user in (role_response.data or [])
                    }
                    for user in users:
                        if isinstance(user, dict):
                            user["user_type"] = roles.get(str(user.get("id")), "user")
                except Exception:
                    # Role metadata must never prevent the core leaderboard
                    # response from loading (for example during schema rollout).
                    logger.exception("Failed to enrich leaderboard user roles")
        return data
