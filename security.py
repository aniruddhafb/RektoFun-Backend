"""HTTP security controls shared by the RektoFun API."""

from __future__ import annotations

import hmac
import logging
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from config import get_settings

logger = logging.getLogger(__name__)

MAX_JSON_BODY_BYTES = 1 * 1024 * 1024
MAX_UPLOAD_BODY_BYTES = 6 * 1024 * 1024
RATE_WINDOW_SECONDS = 60
GENERAL_RATE_LIMIT = 180
MUTATION_RATE_LIMIT = 60
OTP_RATE_LIMIT = 5

_requests: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    host = forwarded or (request.client.host if request.client else "unknown")
    bucket = "otp" if request.url.path == "/email/request-otp" else (
        "mutation" if request.method not in {"GET", "HEAD", "OPTIONS"} else "read"
    )
    return f"{host}:{bucket}"


def _rate_limit_for(request: Request) -> int:
    if request.url.path == "/email/request-otp":
        return OTP_RATE_LIMIT
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return MUTATION_RATE_LIMIT
    return GENERAL_RATE_LIMIT


def enforce_rate_limit(request: Request) -> None:
    now = time.monotonic()
    cutoff = now - RATE_WINDOW_SECONDS
    key = _client_key(request)
    limit = _rate_limit_for(request)
    with _rate_lock:
        timestamps = _requests[key]
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again shortly.",
                headers={"Retry-After": str(RATE_WINDOW_SECONDS)},
            )
        timestamps.append(now)


def body_limit_for(request: Request) -> int:
    if request.url.path == "/api/admin/category-image":
        return MAX_UPLOAD_BODY_BYTES
    return MAX_JSON_BODY_BYTES


def require_internal_api_key(request: Request) -> None:
    expected = get_settings().internal_api_key
    supplied = request.headers.get("x-internal-api-key", "")
    if not expected:
        logger.error("INTERNAL_API_KEY (or CRON_API_KEY fallback) is not configured")
        raise HTTPException(status_code=503, detail="Server authentication is not configured")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Authenticated server request required")


def mutation_requires_internal_auth(request: Request) -> bool:
    path = request.url.path
    if path.startswith("/api/admin/"):
        return True
    if path.startswith("/api/challenges/cron/"):
        return False  # These retain their dedicated cron-key dependency.
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return False
    # Duplicate checks do not mutate data and are intentionally public.
    if path == "/api/challenges/availability":
        return False
    return True
