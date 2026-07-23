from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: int
    recipient_id: int
    actor_id: int
    challenge_id: Optional[int] = None
    event_type: Literal[
        "challenge_created", "challenge_joined", "user_followed", "user_followed_back",
        "challenge_won",
        "challenge_received", "challenge_accepted", "challenge_declined",
    ]
    message: str
    is_read: bool = False
    created_at: datetime
    actor_username: Optional[str] = None
    actor_profile_image: Optional[str] = None
    actor_wallet_address: Optional[str] = None
    invitation_status: Optional[
        Literal["PENDING", "ACCEPTED", "DECLINED", "EXPIRED", "CANCELLED"]
    ] = None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int = Field(ge=0)


class NotificationReadRequest(BaseModel):
    wallet_address: str = Field(min_length=1)
