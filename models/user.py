"""
User models for request/response validation and data transfer.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user model with common attributes"""
    username: Optional[str] = Field(None, description="User's display name")
    email: Optional[EmailStr] = Field(None, description="User's email address")
    pubkey: Optional[str] = Field(None, description="User's Solana public key")
    profile_image: Optional[str] = Field(None, description="URL to user's profile image")
    bio: Optional[str] = Field(None, description="User's bio/description")


class UserCreate(UserBase):
    """Model for creating a new user"""
    pass


class UserUpdate(BaseModel):
    """Model for updating an existing user - all fields optional"""
    username: Optional[str] = Field(None, description="User's display name")
    email: Optional[EmailStr] = Field(None, description="User's email address")
    pubkey: Optional[str] = Field(None, description="User's Solana public key")
    profile_image: Optional[str] = Field(None, description="URL to user's profile image")
    bio: Optional[str] = Field(None, description="User's bio/description")


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


class UsernameCheckResponse(BaseModel):
    """Model for username existence check response"""
    username: str = Field(..., description="The username that was checked")
    exists: bool = Field(..., description="Whether the username is already taken")