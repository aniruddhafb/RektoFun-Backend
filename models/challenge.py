"""
Challenge models for request/response validation and data transfer.
"""

import re
from datetime import date, datetime
from enum import Enum
from typing import Optional, Any, Literal

from pydantic import BaseModel, Field, field_validator

from models.user import UserResponse


class ChallengeStatus(str, Enum):
    """Challenge status enum matching Supabase schema"""
    OPEN = "OPEN"
    PENDING_RESOLUTION = "PENDING_RESOLUTION"
    EXPIRED = "EXPIRED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


class ChallengeMode(str, Enum):
    """Challenge mode enum matching Supabase schema"""
    PVP = "PVP"
    TEAM = "TEAM"


class ResolutionMethod(str, Enum):
    """Resolution method enum matching Supabase schema"""
    PRICE_FEED = "PRICE_FEED"
    COMMUNITY = "COMMUNITY"


class Side(str, Enum):
    """Side/result enum matching Supabase schema"""
    TEAM_A = "TEAM_A"
    TEAM_B = "TEAM_B"


class Direction(str, Enum):
    """Direction enum matching Supabase schema"""
    UP = "UP"
    DOWN = "DOWN"


class ChallengeBase(BaseModel):
    """Base challenge model with common attributes"""
    statement: Optional[str] = Field(None, description="The challenge statement/question")
    ticker: Optional[str] = Field(None, description="The ticker symbol for the challenge")
    trading_pair: Optional[str] = Field(None, description="The trading pair symbol (e.g., BTCUSDT)")
    target: Optional[float] = Field(None, description="Target value for price-based challenges")
    initial_bet: Optional[int] = Field(None, description="Initial bet amount")
    pool_size: Optional[int] = Field(None, description="Total pool size")
    resolution_source: Optional[str] = Field(None, description="Source for resolving the challenge")
    metadata: Optional[dict[str, Any]] = Field(None, description="Additional metadata as JSON")
    creator: Optional[int] = Field(None, description="ID of the user who created the challenge")
    resolution_method: Optional[ResolutionMethod] = Field(None, description="Method for resolving the challenge")
    participants: Optional[int] = Field(None, description="Number of participants")
    status: Optional[ChallengeStatus] = Field(ChallengeStatus.OPEN, description="Challenge status")
    mode: Optional[ChallengeMode] = Field(None, description="Challenge mode (PVP or TEAM)")
    result: Optional[Side] = Field(None, description="Result side if resolved")
    direction: Optional[Direction] = Field(None, description="Direction of the challenge (UP or DOWN)")
    expiry: Optional[datetime] = Field(None, description="This is the timestamp when new bets will no longer be accepted for the challenge")
    resolution_date: Optional[date] = Field(None, description="Date when the challenge will be resolved")
    final_price: Optional[float] = Field(None, description="Final price of the asset when challenge was resolved or expired")
    category: Optional[str] = Field(None, description="Category of the challenge")
    bet_info: Optional[dict[str, Any]] = Field(None, description="Additional bet metadata as JSON; includes a 'highest_bet' key holding the highest bet per side (TEAM_A/TEAM_B), each holding id/username/profile_image/pubkey/bet/twitter_username/user_type, and a 'team_count' key holding total_bets (count) and total_amount (sum of bets) per side (TEAM_A/TEAM_B)")
    visibility: Literal["PUBLIC", "DIRECT"] = Field("PUBLIC", description="Whether anyone or only an invited user may join")
    challenged_user_id: Optional[int] = Field(None, description="Recipient of a direct PVP invitation")
    invitation_status: Optional[Literal["PENDING", "ACCEPTED", "DECLINED", "EXPIRED", "CANCELLED"]] = None


class ChallengeCreate(ChallengeBase):
    """Model for creating a new challenge"""

    @field_validator("statement")
    @classmethod
    def remove_will_be_from_statement(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        statement = re.sub(r"\bwill\s+be\b", "", value, flags=re.IGNORECASE)
        return re.sub(r"\s{2,}", " ", statement).strip()

    @field_validator("ticker")
    @classmethod
    def store_base_ticker_only(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        return value.split("/", 1)[0].strip().upper()


class ChallengeAvailabilityResponse(BaseModel):
    """Whether a proposed challenge is sufficiently different from active ones."""
    allowed: bool
    reason: Optional[str] = None
    available_at: Optional[datetime] = None
    conflicting_challenge_ids: list[int] = Field(default_factory=list)


class ChallengeUpdate(BaseModel):
    """Model for updating an existing challenge - all fields optional"""
    statement: Optional[str] = Field(None, description="The challenge statement/question")
    ticker: Optional[str] = Field(None, description="The ticker symbol for the challenge")
    trading_pair: Optional[str] = Field(None, description="The trading pair symbol (e.g., BTCUSDT)")
    target: Optional[float] = Field(None, description="Target value for price-based challenges")
    initial_bet: Optional[int] = Field(None, description="Initial bet amount")
    pool_size: Optional[int] = Field(None, description="Total pool size")
    resolution_source: Optional[str] = Field(None, description="Source for resolving the challenge")
    metadata: Optional[dict[str, Any]] = Field(None, description="Additional metadata as JSON")
    creator: Optional[int] = Field(None, description="ID of the user who created the challenge")
    resolution_method: Optional[ResolutionMethod] = Field(None, description="Method for resolving the challenge")
    participants: Optional[int] = Field(None, description="Number of participants")
    status: Optional[ChallengeStatus] = Field(None, description="Challenge status")
    mode: Optional[ChallengeMode] = Field(None, description="Challenge mode (PVP or TEAM)")
    result: Optional[Side] = Field(None, description="Result side if resolved")
    direction: Optional[Direction] = Field(None, description="Direction of the challenge (UP or DOWN)")
    expiry: Optional[datetime] = Field(None, description="Expiry timestamp for the challenge")
    resolution_date: Optional[date] = Field(None, description="Date when the challenge will be resolved")
    final_price: Optional[float] = Field(None, description="Final price of the asset when challenge was resolved or expired")
    category: Optional[str] = Field(None, description="Category of the challenge")
    bet_info: Optional[dict[str, Any]] = Field(None, description="Additional bet metadata as JSON; includes a 'highest_bet' key holding the highest bet per side (TEAM_A/TEAM_B), each holding id/username/profile_image/pubkey/bet/twitter_username/user_type, and a 'team_count' key holding total_bets (count) and total_amount (sum of bets) per side (TEAM_A/TEAM_B)")


class ChallengeResponse(ChallengeBase):
    """Model for challenge response data"""
    id: int = Field(..., description="Unique challenge ID")
    views: int = Field(0, ge=0, description="Number of times the challenge detail was opened")
    created_at: datetime = Field(..., description="Challenge creation timestamp")
    resolved_at: Optional[datetime] = Field(None, description="Exact UTC resolution timestamp")
    category_image: Optional[str] = Field(None, description="Image associated with the challenge category")
    creator_details: Optional[UserResponse] = Field(None, description="Details of the user who created the challenge")
    challenged_user_details: Optional[UserResponse] = Field(None, description="Invited user for a direct challenge")

    class Config:
        from_attributes = True


class ChallengeListResponse(BaseModel):
    """Model for list of challenges response"""
    challenges: list[ChallengeResponse]
    total: int = Field(..., description="Total number of challenges")
    has_more: bool = Field(False, description="Whether another page is available")


class ChallengeViewResponse(BaseModel):
    """Response returned after recording a challenge view."""
    challenge_id: int = Field(..., description="Viewed challenge ID")
    views: int = Field(..., ge=0, description="Updated challenge view count")
