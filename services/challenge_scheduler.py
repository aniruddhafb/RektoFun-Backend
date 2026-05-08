"""
Challenge resolution scheduler.

Schedules a one-shot resolution job for every crypto challenge at its resolve_time.  Uses APScheduler's AsyncIOScheduler so it runs inside the
same event-loop as FastAPI — no extra processes or queues needed.

On startup it also re-schedules any open crypto challenges that are still
in the future, so a server restart never silently drops a pending job.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from supabase import Client

from services.dia_price import get_asset_price

# Parent market name for crypto child markets (Bitcoin, Ethereum, Solana, etc.)
# Child markets have parent_name = "crypto"; the parent market itself has parent_id = NULL.
_CRYPTO_PARENT_NAME = "crypto"


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class ChallengeScheduler:
    """
    Manages timed resolution of crypto challenges.

    Usage (wired up in main.py lifespan):
        scheduler = ChallengeScheduler(supabase_client)
        scheduler.start()          # call once on app startup
        scheduler.schedule_challenge(challenge_id, resolve_time)
        await scheduler.stop()     # call on app shutdown
    """

    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler and re-schedule any open crypto challenges."""
        self._scheduler.start()
        # Fire-and-forget recovery task so start() stays synchronous
        asyncio.create_task(self._recover_pending_challenges(), name="challenge-scheduler-recovery")
        print("[Scheduler] Started.")

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        self._scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule_challenge(self, challenge_id: str, resolve_time: datetime) -> None:
        """
        Schedule a one-shot resolution job for a challenge.

        If resolve_time is already in the past the job fires immediately
        (APScheduler behaviour with a past DateTrigger).

        Args:
            challenge_id: UUID string of the challenge.
            resolve_time:  Timezone-aware datetime when the challenge should resolve.
        """
        job_id = f"resolve_{challenge_id}"

        # Avoid duplicate jobs (e.g. called twice for the same challenge)
        if self._scheduler.get_job(job_id):
            print(f"[Scheduler] Job {job_id} already exists, skipping.")
            return

        # Ensure the datetime is timezone-aware
        if resolve_time.tzinfo is None:
            resolve_time = resolve_time.replace(tzinfo=timezone.utc)

        self._scheduler.add_job(
            self._resolve_challenge,
            trigger=DateTrigger(run_date=resolve_time),
            id=job_id,
            args=[challenge_id],
            misfire_grace_time=300,  # allow up to 5 min late if scheduler was busy
            replace_existing=True,
        )
        print(f"[Scheduler] Scheduled resolution for challenge {challenge_id} at {resolve_time.isoformat()}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _recover_pending_challenges(self) -> None:
        """
        On startup, re-schedule all open crypto challenges whose
        resolve_time is still in the future.
        """
        try:
            now_iso = _now_utc().isoformat()
            result = (
                self._supabase.table("challenges")
                .select("id, resolve_time, category, asset_name")
                .eq("status", "open")
                .gt("resolve_time", now_iso)
                .execute()
            )
            rows = result.data or []
            if not rows:
                print("[Scheduler] No pending challenges to recover.")
                return

            # Fetch parent_name for all relevant markets in one query.
            # Crypto child markets have parent_name = "crypto".
            category_names = list({row["category"] for row in rows if row.get("category")})
            markets_res = (
                self._supabase.table("markets")
                .select("name, parent_name")
                .in_("name", category_names)
                .execute()
            )
            crypto_markets: set[str] = {
                m["name"]
                for m in (markets_res.data or [])
                if (m.get("parent_name") or "").lower() == _CRYPTO_PARENT_NAME
            }

            recovered = 0
            for row in rows:
                if row.get("category") not in crypto_markets:
                    continue
                resolve_time = _parse_dt(row.get("resolve_time"))
                if resolve_time is None:
                    continue
                self.schedule_challenge(row["id"], resolve_time)
                recovered += 1

            print(f"[Scheduler] Recovered {recovered} pending crypto challenge(s).")
        except Exception as exc:
            print(f"[Scheduler] Error during recovery: {exc}")

    async def _resolve_challenge(self, challenge_id: str) -> None:
        """
        Job function — called by APScheduler at resolve_time.

        Steps:
          1. Fetch the challenge row.
          2. Guard: skip if already resolved/cancelled.
          3. Fetch current price from DIA.
          4. Determine outcome (YES / NO) vs target_price.
          5. Update the challenge row in Supabase.
        """
        print(f"[Scheduler] Resolving challenge {challenge_id} ...")

        try:
            # 1. Fetch challenge
            res = (
                self._supabase.table("challenges")
                .select("id, status, asset_name, target_price, resolution_status")
                .eq("id", challenge_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if not rows:
                print(f"[Scheduler] Challenge {challenge_id} not found, skipping.")
                return

            challenge = rows[0]

            # 2. Guard
            if challenge.get("status") in ("resolved", "cancelled"):
                print(f"[Scheduler] Challenge {challenge_id} already {challenge['status']}, skipping.")
                return

            asset_name: str | None = challenge.get("asset_name")
            target_price: int | None = challenge.get("target_price")

            if not asset_name:
                print(f"[Scheduler] Challenge {challenge_id} has no asset_name, cannot resolve.")
                await self._mark_failed(challenge_id, reason="no asset_name")
                return

            # Mark as fetching so we don't double-resolve on a retry
            self._supabase.table("challenges").update(
                {"resolution_status": "fetching"}
            ).eq("id", challenge_id).execute()

            # 3. Fetch price using asset_name (e.g. "Bitcoin", "Ethereum", "Solana")
            #    asset_name matches the DIA blockchain name directly — no mapping needed.
            price = await get_asset_price(asset_name)
            if price is None:
                print(f"[Scheduler] Could not fetch price for asset_name={asset_name}, marking failed.")
                await self._mark_failed(challenge_id, reason=f"price fetch failed for asset_name={asset_name}")
                return

            # 4. Determine outcome
            outcome = _determine_outcome(price, target_price)

            # 5. Update challenge
            now_iso = _now_utc().isoformat()
            update_payload: dict[str, Any] = {
                "status": "resolved",
                "resolution_status": "resolved",
                "resolved_at": now_iso,
                "result": {
                    "outcome": outcome,
                    "price_at_resolve": price,
                    "target_price": target_price,
                    "source": "diadata.org",
                    "resolved_at": now_iso,
                },
            }

            self._supabase.table("challenges").update(update_payload).eq("id", challenge_id).execute()
            print(
                f"[Scheduler] Challenge {challenge_id} resolved → outcome={outcome} "
                f"price={price} target={target_price}"
            )

        except Exception as exc:
            print(f"[Scheduler] Unexpected error resolving challenge {challenge_id}: {exc}")
            await self._mark_failed(challenge_id, reason=str(exc))

    async def _mark_failed(self, challenge_id: str, reason: str = "") -> None:
        """Set resolution_status to 'failed' without changing the challenge status."""
        try:
            self._supabase.table("challenges").update(
                {
                    "resolution_status": "failed",
                    "result": {"error": reason},
                }
            ).eq("id", challenge_id).execute()
        except Exception as exc:
            print(f"[Scheduler] Could not mark challenge {challenge_id} as failed: {exc}")


# ------------------------------------------------------------------
# Pure helpers
# ------------------------------------------------------------------

def _determine_outcome(price: float, target_price: int | None) -> str:
    """
    Determine YES/NO outcome for a binary crypto challenge.

    YES  → price reached or exceeded target_price
    NO   → price is below target_price
    N/A  → no target_price set (caller should handle this case)
    """
    if target_price is None:
        return "N/A"
    return "YES" if price >= target_price else "NO"


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string into a timezone-aware datetime."""
    if not value:
        return None
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None

