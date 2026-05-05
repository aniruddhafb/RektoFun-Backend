"""Models for markets."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MarketType(str, Enum):
    """Market type enumeration."""
    binary = "binary"
    multi_outcome = "multi_outcome"
    numeric_range = "numeric_range"
    categorical = "categorical"


class MarketCreate(BaseModel):
    """Schema for creating a market."""
    name: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    description: str | None = None
    image: str | None = None
    icon: str | None = None
    parent_id: str | None = None
    parent_name: str | None = None
    market_type: MarketType
    resolution_source: str | None = None
    config: dict | None = None
    is_active: bool = True


class MarketUpdate(BaseModel):
    """Schema for updating a market."""
    name: str | None = None
    symbol: str | None = None
    description: str | None = None
    image: str | None = None
    icon: str | None = None
    parent_id: str | None = None
    parent_name: str | None = None
    market_type: MarketType | None = None
    resolution_source: str | None = None
    config: dict | None = None
    total_volume: int | None = None
    is_active: bool | None = None


class MarketResponse(BaseModel):
    """Schema for market response."""
    id: str
    name: str
    symbol: str
    description: str | None
    image: str | None
    icon: str | None
    parent_id: str | None
    parent_name: str | None
    market_type: str
    resolution_source: str | None
    config: dict | None
    total_volume: int
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


class MarketListResponse(BaseModel):
    """Schema for market list response."""
    markets: list[MarketResponse]
    count: int
