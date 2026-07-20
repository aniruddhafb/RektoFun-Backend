"""Internal, database-backed rate-limit checks."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import get_service_supabase_client

router = APIRouter()


class WithdrawalRateLimitRequest(BaseModel):
    identifier: str = Field(pattern=r"^[0-9a-f]{64}$")


class WithdrawalRateLimitResponse(BaseModel):
    allowed: bool
    retry_after_seconds: int


@router.post(
    "/internal/withdrawal-rate-limit",
    response_model=WithdrawalRateLimitResponse,
)
def check_withdrawal_rate_limit(
    payload: WithdrawalRateLimitRequest,
) -> WithdrawalRateLimitResponse:
    """Atomically consume the minute and hour counters for a hashed client IP."""
    try:
        response = get_service_supabase_client().rpc(
            "check_withdrawal_ip_rate_limit",
            {"p_identifier": payload.identifier},
        ).execute()
        rows = response.data
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("Rate-limit RPC returned no result")
        row = rows[0]
        allowed = row.get("allowed")
        retry_after = row.get("retry_after_seconds")
        if not isinstance(allowed, bool) or not isinstance(retry_after, int):
            raise RuntimeError("Rate-limit RPC returned an invalid result")
        return WithdrawalRateLimitResponse(
            allowed=allowed,
            retry_after_seconds=max(0, retry_after),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Withdrawal rate limiting is temporarily unavailable",
        ) from exc
