"""
Challenge models for request/response validation and data transfer.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field


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
    target: Optional[int] = Field(None, description="Target value for price-based challenges")
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
    expiry: Optional[date] = Field(None, description="This is the date when new bets will no longer be accepted for the challenge")
    resolution_date: Optional[date] = Field(None, description="Date when the challenge will be resolved")
    final_price: Optional[int] = Field(None, description="Final price of the asset when challenge was resolved or expired")
    category: Optional[str] = Field(None, description="Category of the challenge")


class ChallengeCreate(ChallengeBase):
    """Model for creating a new challenge"""
    pass


class ChallengeUpdate(BaseModel):
    """Model for updating an existing challenge - all fields optional"""
    statement: Optional[str] = Field(None, description="The challenge statement/question")
    ticker: Optional[str] = Field(None, description="The ticker symbol for the challenge")
    trading_pair: Optional[str] = Field(None, description="The trading pair symbol (e.g., BTCUSDT)")
    target: Optional[int] = Field(None, description="Target value for price-based challenges")
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
    expiry: Optional[date] = Field(None, description="Expiry date for the challenge")
    resolution_date: Optional[date] = Field(None, description="Date when the challenge will be resolved")
    final_price: Optional[int] = Field(None, description="Final price of the asset when challenge was resolved or expired")
    category: Optional[str] = Field(None, description="Category of the challenge")


class ChallengeResponse(ChallengeBase):
    """Model for challenge response data"""
    id: int = Field(..., description="Unique challenge ID")
    created_at: datetime = Field(..., description="Challenge creation timestamp")

    class Config:
        from_attributes = True


class ChallengeListResponse(BaseModel):
    """Model for list of challenges response"""
    challenges: list[ChallengeResponse]
    total: int = Field(..., description="Total number of challenges")