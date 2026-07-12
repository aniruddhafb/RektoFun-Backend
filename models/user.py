"""
User models for request/response validation and data transfer.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user model with common attributes"""
    username: Optional[str] = Field(None, description="User's display name")
    email: Optional[EmailStr] = Field(None, description="User's email address")
    pubkey: Optional[str] = Field(None, description="User's Solana public key")
    profile_image: Optional[str] = Field(None, description="URL to user's profile image")
    bio: Optional[str] = Field(None, description="User's bio/description")
    twitter_username: Optional[str] = Field(None, max_length=15, description="User's X/Twitter username")
    referral_code: Optional[str] = Field(None, description="User's referral code")
    referred_by: Optional[str] = Field(None, description="Referral code used by this user")
    referrals: list[str] = Field(default_factory=list, description="Wallets referred by this user")
    followers: list[int] = Field(default_factory=list, description="IDs of users following this user")
    following: list[int] = Field(default_factory=list, description="IDs of users this user follows")
    user_type: Literal["user", "moderator"] = Field("user", description="Account role; moderators earn a 40% referral fee share")


class UserCreate(UserBase):
    """Model for creating a new user"""
    referrer_code: Optional[str] = Field(None, description="Referral code to apply after creating the user")


class UserUpdate(BaseModel):
    """Model for updating an existing user - all fields optional"""
    username: Optional[str] = Field(None, description="User's display name")
    email: Optional[EmailStr] = Field(None, description="User's email address")
    pubkey: Optional[str] = Field(None, description="User's Solana public key")
    profile_image: Optional[str] = Field(None, description="URL to user's profile image")
    bio: Optional[str] = Field(None, description="User's bio/description")
    twitter_username: Optional[str] = Field(None, max_length=15, description="User's X/Twitter username")


class UserResponse(UserBase):
    """Model for user response data"""
    id: int = Field(..., description="Unique user ID")
    created_at: datetime = Field(..., description="User creation timestamp")

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Model for list of users response"""
    users: list[UserResponse]
    total: int = Field(..., description="Total number of users")


class LeaderboardUserResponse(UserResponse):
    """A user enriched with realized challenge statistics."""
    rank: int
    won: int
    lost: int
    win_rate: float
    pnl: float
    volume: float


class LeaderboardSummary(BaseModel):
    total_users: int
    total_challenges: int
    total_volume: float
    total_pnl: float


class LeaderboardResponse(BaseModel):
    users: list[LeaderboardUserResponse]
    total: int
    period: str
    summary: LeaderboardSummary


class UsernameCheckResponse(BaseModel):
    """Model for username existence check response"""
    username: str = Field(..., description="The username that was checked")
    exists: bool = Field(..., description="Whether the username is already taken")


class AcceptReferralRequest(BaseModel):
    """Model for accepting a referral code"""
    new_user_wallet: str = Field(..., description="Wallet/public key of the user accepting the referral")
    referrer_code: str = Field(..., description="Referral code provided by the referrer")


class FollowRequest(BaseModel):
    """Identify the user performing a follow action."""
    follower_wallet: str = Field(..., min_length=1, description="Wallet/public key of the acting user")
