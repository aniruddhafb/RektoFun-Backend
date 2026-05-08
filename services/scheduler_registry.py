"""
Scheduler registry — holds the singleton ChallengeScheduler instance.

This module exists purely to break the circular import that would occur if
routes/challenges.py imported from main.py.

Usage:
    # In main.py (set once at startup):
    from services.scheduler_registry import set_scheduler
    set_scheduler(ChallengeScheduler(...))

    # In routes/challenges.py (read at request time):
    from services.scheduler_registry import get_scheduler
    scheduler = get_scheduler()
    if scheduler:
        scheduler.schedule_challenge(challenge_id, expire_time)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.challenge_scheduler import ChallengeScheduler

_scheduler: "ChallengeScheduler | None" = None


def set_scheduler(scheduler: "ChallengeScheduler") -> None:
    """Register the global scheduler instance (called once from main.py)."""
    global _scheduler
    _scheduler = scheduler


def get_scheduler() -> "ChallengeScheduler | None":
    """Return the global scheduler instance, or None if not yet initialised."""
    return _scheduler
