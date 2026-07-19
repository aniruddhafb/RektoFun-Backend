"""Database-side leaderboard queries designed for large user populations."""

import logging
from datetime import datetime, timedelta, timezone
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
        rank_by_created = sort in ("created_challenges", "rank")
        response = self.db.rpc("get_challenge_leaderboard", {
            "p_period": period,
            # Verification is user metadata rather than an aggregate held by
            # the legacy RPC. Fetch the ranked set before applying this filter
            # so pagination and totals remain correct.
            "p_limit": 10000 if filtered or rank_by_created else limit,
            "p_offset": 0 if filtered or rank_by_created else offset,
            "p_search": search,
            # Creation ranking is applied below because the legacy RPC only
            # knows realized trading metrics.
            "p_sort": "pnl" if rank_by_created else sort,
            "p_order": order,
        }).execute()
        data = response.data
        if not isinstance(data, dict):
            raise RuntimeError("Leaderboard database function returned an invalid response")

        # PostgreSQL caps this legacy RPC at 100 rows per call. Creation and
        # verification ranking must operate on the complete matching user set,
        # otherwise a prolific creator outside the first P&L page disappears.
        if filtered or rank_by_created:
            users = data.get("users")
            total = int(data.get("total") or 0)
            if isinstance(users, list):
                all_users = list(users)
                while all_users and len(all_users) < total:
                    next_page = self.db.rpc("get_challenge_leaderboard", {
                        "p_period": period,
                        "p_limit": 1000,
                        "p_offset": len(all_users),
                        "p_search": search,
                        "p_sort": "pnl" if rank_by_created else sort,
                        "p_order": order,
                    }).execute().data
                    if not isinstance(next_page, dict):
                        raise RuntimeError("Leaderboard database function returned an invalid page")
                    page_users = next_page.get("users")
                    if not isinstance(page_users, list) or not page_users:
                        break
                    all_users.extend(page_users)
                data["users"] = all_users

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
            if rank_by_created:
                created_counts: dict[str, int] = {}
                page_size = 1000
                start = 0
                cutoff = None
                if period != "all":
                    cutoff = datetime.now(timezone.utc) - timedelta(
                        days={"1d": 1, "7d": 7, "30d": 30}[period]
                    )

                while True:
                    query = self.db.table("challenge").select("creator")
                    if cutoff is not None:
                        query = query.gte("created_at", cutoff.isoformat())
                    batch = query.range(start, start + page_size - 1).execute().data or []
                    for challenge in batch:
                        creator = challenge.get("creator")
                        if creator is not None:
                            key = str(creator)
                            created_counts[key] = created_counts.get(key, 0) + 1
                    if len(batch) < page_size:
                        break
                    start += page_size

                for user in users:
                    user["created_challenges"] = created_counts.get(str(user.get("id")), 0)

                reverse = order == "desc"
                users.sort(
                    key=lambda user: (
                        user.get("created_challenges", 0),
                        user.get("pnl", 0),
                        -int(user.get("id", 0)),
                    ),
                    reverse=reverse,
                )
                for index, user in enumerate(users, start=1):
                    user["rank"] = index
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
        elif rank_by_created and isinstance(users, list):
            data["total"] = len(users)
            data["users"] = users[offset:offset + limit]
        return data
