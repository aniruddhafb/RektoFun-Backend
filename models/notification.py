from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: int
    recipient_id: int
    actor_id: int
    challenge_id: int
    event_type: Literal["challenge_created", "challenge_joined"]
    message: str
    is_read: bool = False
    created_at: datetime
    actor_username: Optional[str] = None
    actor_profile_image: Optional[str] = None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int = Field(ge=0)


class NotificationReadRequest(BaseModel):
    wallet_address: str = Field(min_length=1)
