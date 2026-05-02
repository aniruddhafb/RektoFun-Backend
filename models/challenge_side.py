"""Models for challenge sides."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class SideKey(str, Enum):
    SUPPORTER = "supporter"
    OPPONENT = "opponent"


class ChallengeSideCreate(BaseModel):
    challenge_id: UUID
    side_key: SideKey
    display_name: SideKey
    total_amount: int = Field(default=0, ge=0)


class ChallengeSideUpdate(BaseModel):
    side_key: SideKey | None = None
    display_name: SideKey | None = None
    total_amount: int | None = None


class ChallengeSideResponse(BaseModel):
    id: str
    challenge_id: UUID
    side_key: SideKey
    display_name: SideKey
    total_amount: int
    created_at: datetime | None


class ChallengeSideListResponse(BaseModel):
    sides: list[ChallengeSideResponse]
    count: int
