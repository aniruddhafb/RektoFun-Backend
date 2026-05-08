"""Models for challenges."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from models.challenge_side import SideKey


class ChallengeStatus(str, Enum):
    open = "open"
    locked = "locked"
    resolved = "resolved"
    cancelled = "cancelled"


class EventType(str, Enum):
    binary = "binary"
    multi_outcome = "multi_outcome"
    numeric_range = "numeric_range"


class ResolutionStatus(str, Enum):
    pending = "pending"
    fetching = "fetching"
    resolved = "resolved"
    failed = "failed"
    disputed = "disputed"


class ResolutionMode(str, Enum):
    at_time = "at_time"
    anytime_before = "anytime_before"
    event_based = "event_based"


class Mode(str, Enum):
    pvp = "pvp"
    pool = "pool"


class ChallengeCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    category: str = Field(description="Reference to markets name")
    asset_name: str | None = None
    event_type: EventType
    ticker: str | None = None
    target_price: int | None = None
    created_by: str | None = None
    mode: Mode = Field(default=Mode.pool)
    initial_bet: int = Field(ge=0)
    min_accept_bet: int | None = None
    max_accept_bet: int | None = None
    min_bet: int = Field(default=1, ge=1)
    bet_unit: int = Field(default=1, ge=1)
    expire_time: datetime
    resolve_time: datetime
    resolution_source: str | None = None
    resolution_config: dict = Field(default_factory=dict)
    result: dict | None = None
    metadata: dict | None = None


class ChallengeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    asset_name: str | None = None
    event_type: EventType | None = None
    ticker: str | None = None
    target_price: int | None = None
    mode: Mode | None = None
    initial_bet: int | None = None
    min_accept_bet: int | None = None
    max_accept_bet: int | None = None
    min_bet: int | None = None
    bet_unit: int | None = None
    total_challengers: int | None = None
    total_opponents: int | None = None
    status: ChallengeStatus | None = None
    resolution_status: ResolutionStatus | None = None
    resolution_mode: ResolutionMode | None = None
    resolution_source: str | None = None
    resolution_config: dict | None = None
    expire_time: datetime | None = None
    resolve_time: datetime | None = None
    resolved_at: datetime | None = None
    result: dict | None = None
    metadata: dict | None = None


class ChallengeResponse(BaseModel):
    id: str
    title: str
    description: str | None
    category: str
    asset_name: str | None
    event_type: str
    ticker: str | None
    target_price: int | None
    created_by: str | None
    mode: str
    initial_bet: int
    min_accept_bet: int | None
    max_accept_bet: int | None
    min_bet: int
    bet_unit: int
    total_pool: int
    total_challengers: int
    total_opponents: int
    status: str
    resolution_status: str
    resolution_mode: str
    resolution_source: str | None
    resolution_config: dict
    expire_time: datetime
    resolve_time: datetime | None
    resolved_at: datetime | None
    result: dict | None
    metadata: dict | None
    created_at: datetime | None
    updated_at: datetime | None


class EnrichedChallengeResponse(BaseModel):
    id: str
    title: str
    asset_name: str | None
    mode: str
    initial_bet: int
    target_price: int | None
    min_accept_bet: int | None
    max_accept_bet: int | None
    min_bet: int
    total_pool: int
    status: str
    resolution_status: str | None = None
    resolution_source: str | None = None
    expire_time: datetime
    resolve_time: datetime | None
    resolved_at: datetime | None
    result: dict | None
    metadata: dict | None
    created_at: datetime | None
    total_challengers: int
    total_opponents: int
    market: dict | None = Field(description="Market info: name, image, icon, parent_id, parent_name")
    creator: dict | None = Field(description="Creator info: username, profile_image")
    opponent_info: dict | None = Field(description="First challenge_side data with SideKey = opponent")

class ChallengeListResponse(BaseModel):
    challenges: list[EnrichedChallengeResponse]
    count: int


class ChallengeJoin(BaseModel):
    challenge_id: UUID
    user_id: str 
    side: SideKey
    bet_amount: int = Field(ge=1)
