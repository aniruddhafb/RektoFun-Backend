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
        sort: str, order: str, verification: str = "all",
    ) -> dict[str, Any]:
        """Delegate aggregation, ranking and pagination to PostgreSQL."""
        filtered = verification != "all"
        response = self.db.rpc("get_challenge_leaderboard", {
            "p_period": period,
            # Verification is user metadata rather than an aggregate held by
            # the legacy RPC. Fetch the ranked set before applying this filter
            # so pagination and totals remain correct.
            "p_limit": 10000 if filtered else limit,
            "p_offset": 0 if filtered else offset,
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
                        self.db.table("user")
                        .select("id,user_type,twitter_username")
                        .in_("id", user_ids)
                        .execute()
                    )
                    roles = {
                        str(user["id"]): user
                        for user in (role_response.data or [])
                    }
                    for user in users:
                        if isinstance(user, dict):
                            profile = roles.get(str(user.get("id")), {})
                            user["user_type"] = profile.get("user_type", "user")
                            user["twitter_username"] = profile.get("twitter_username")
                except Exception:
                    # Role metadata must never prevent the core leaderboard
                    # response from loading (for example during schema rollout).
                    logger.exception("Failed to enrich leaderboard user roles")
        if filtered and isinstance(users, list):
            if verification == "x":
                users = [
                    user for user in users
                    if user.get("user_type") != "moderator" and user.get("twitter_username")
                ]
            elif verification == "kol":
                users = [user for user in users if user.get("user_type") == "moderator"]
            data["total"] = len(users)
            data["users"] = users[offset:offset + limit]
        return data
