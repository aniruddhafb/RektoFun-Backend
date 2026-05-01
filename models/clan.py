"""Models for clan system."""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class ClanCreate(BaseModel):
    """Model for creating a new clan."""
    clan_name: str = Field(min_length=1, max_length=100)
    clan_description: Optional[str] = Field(default=None, max_length=1000)
    clan_image: Optional[str] = Field(default=None)
    max_members: int = Field(default=50, ge=5, le=100)
    clan_status: str = Field(default="public")  # "public" or "invite_only"
    clan_region: Optional[str] = Field(default=None)
    clan_leader: str = Field(min_length=1)  # User ID, not wallet address


class ClanUpdate(BaseModel):
    """Model for updating an existing clan."""
    clan_name: str = Field(min_length=1, max_length=100)
    clan_description: Optional[str] = Field(default=None, max_length=1000)
    clan_image: Optional[str] = Field(default=None)
    max_members: int = Field(default=50, ge=5, le=100)
    clan_status: str = Field(default="public")  # "public" or "invite_only"
    clan_region: Optional[str] = Field(default=None)


class ClanResponse(BaseModel):
    """Model for clan response data."""
    id: str
    clan_name: str
    clan_description: Optional[str] = None
    clan_image: Optional[str] = None
    max_members: int
    clan_leader: str
    clan_members: List[str] = []
    clan_status: str
    clan_region: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClanMessageCreate(BaseModel):
    clan_id: str = Field(min_length=1)
    sender_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)


class ClanMessageResponse(BaseModel):
    id: str
    clan_id: str
    sender_id: str
    message: str
    created_at: datetime
    sender_username: str | None = None
    sender_avatar: str | None = None


class ClanMessageListResponse(BaseModel):
    messages: list[ClanMessageResponse]
    count: int


def coerce_clan_message(row: dict) -> ClanMessageResponse:
    return ClanMessageResponse.model_validate(row)
