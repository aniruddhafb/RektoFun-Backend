"""
Position models for request/response validation and data transfer.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Side(str, Enum):
    """Side enum matching Supabase schema"""
    TEAM_A = "TEAM_A"
    TEAM_B = "TEAM_B"


class PositionBase(BaseModel):
    """Base position model with common attributes"""
    challenge_id: Optional[int] = Field(None, description="ID of the challenge")
    bet: Optional[int] = Field(None, description="Bet amount")
    side: Optional[Side] = Field(None, description="Side chosen (TEAM_A or TEAM_B)")
    creator: Optional[int] = Field(None, description="ID of the user who created the position")


class PositionCreate(PositionBase):
    """Model for creating a new position"""
    pass


class PositionUpdate(BaseModel):
    """Model for updating an existing position - all fields optional"""
    challenge_id: Optional[int] = Field(None, description="ID of the challenge")
    bet: Optional[int] = Field(None, description="Bet amount")
    side: Optional[Side] = Field(None, description="Side chosen (TEAM_A or TEAM_B)")
    creator: Optional[int] = Field(None, description="ID of the user who created the position")


class PositionResponse(PositionBase):
    """Model for position response data"""
    id: int = Field(..., description="Unique position ID")
    created_at: datetime = Field(..., description="Position creation timestamp")

    class Config:
        from_attributes = True


class PositionParticipantUser(BaseModel):
    """Public user fields needed by the challenge detail modal."""
    id: int
    username: Optional[str] = None
    pubkey: Optional[str] = None
    profile_image: Optional[str] = None
    twitter_username: Optional[str] = None
    user_type: str = "user"


class ChallengeParticipantPosition(PositionResponse):
    """A position with its participant resolved in the same database query."""
    user: Optional[PositionParticipantUser] = None


class PositionListResponse(BaseModel):
    """Model for list of positions response"""
    positions: list[PositionResponse]
    total: int = Field(..., description="Total number of positions")
