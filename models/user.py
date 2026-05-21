"""Models for users."""

from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    wallet_address: str = Field(min_length=1)
    username: str | None = None
    description: str | None = None
    profile_image: str | None = None
    login_type: str = Field(default="wallet", min_length=1)
    referral_code: str | None = None
    referred_by: str | None = None


class UserUpdate(BaseModel):
    username: str | None = None
    description: str | None = None
    profile_image: str | None = None


class UserResponse(BaseModel):
    id: str
    wallet_address: str
    username: str | None
    description: str | None
    profile_image: str | None
    login_type: str
    referral_code: str | None
    referred_by: str | None
    referrals: list[str]
    followers: list[str] = []
    following: list[str] = []
    created_at: datetime | None
    updated_at: datetime | None
    earnings: float | None


class FollowActionRequest(BaseModel):
    follower_wallet_address: str = Field(min_length=1)


class FollowStatusResponse(BaseModel):
    is_following: bool


class UserListResponse(BaseModel):
    users: list[UserResponse]
    count: int
