"""Database-side leaderboard queries designed for large user populations."""

from typing import Any

from supabase import Client


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
        return data
