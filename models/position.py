"""Models for positions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PositionCreate(BaseModel):
    challenge_id: UUID
    side_id: str
    user_id: UUID
    amount: int = Field(ge=1)


class PositionUpdate(BaseModel):
    amount: int | None = None


class PositionResponse(BaseModel):
    id: str
    challenge_id: UUID
    side_id: str
    user_id: UUID
    amount: int
    created_at: datetime | None


class PositionListResponse(BaseModel):
    positions: list[PositionResponse]
    count: int
