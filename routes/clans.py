"""Clan chat API endpoints."""

from typing import Annotated, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from config import get_supabase
from models.clan import (
    ClanCreate,
    ClanUpdate,
    ClanMessageCreate,
    ClanMessageListResponse,
    ClanMessageResponse,
    ClanResponse,
    coerce_clan_message,
)

router = APIRouter(prefix="/clans", tags=["clans"])


class ClanMemberInfo(BaseModel):
    """Model for clan member information with user details."""
    id: str
    username: str | None = None
    profile_image: str | None = None
    earnings: float | None = None
    role: str  # "Leader" or "Member"
    wallet_address: str | None = None


class ClanMembersResponse(BaseModel):
    """Response model for clan members list."""
    members: List[ClanMemberInfo]
    count: int


class PaginatedClansResponse(BaseModel):
    """Response model for paginated clans list."""
    clans: List[ClanResponse]
    total: int
    limit: int
    offset: int


@router.get("", response_model=PaginatedClansResponse)
def get_clans(
    supabase: Annotated[Client, Depends(get_supabase)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedClansResponse:
    """
    Get all clans with pagination.

    Example:
        curl "http://localhost:8000/clans?limit=10&offset=0"
    """
    try:
        # Get total count
        count_result = (
            supabase.table("clans")
            .select("*", count="exact")
            .execute()
        )
        total = count_result.count or 0

        # Get paginated clans
        result = (
            supabase.table("clans")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch clans: {str(exc)}",
        ) from exc

    clans = result.data or []
    return PaginatedClansResponse(
        clans=[
            ClanResponse(
                id=clan["id"],
                clan_name=clan["clan_name"],
                clan_description=clan.get("clan_description"),
                clan_image=clan.get("clan_image"),
                max_members=clan["max_members"],
                clan_leader=clan["clan_leader"],
                clan_members=clan.get("clan_members", []),
                clan_status=clan["clan_status"],
                clan_region=clan.get("clan_region"),
                created_at=clan.get("created_at"),
                updated_at=clan.get("updated_at"),
            )
            for clan in clans
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{clan_id}", response_model=ClanResponse)
def get_clan(
    clan_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ClanResponse:
    """
    Get a single clan by ID.

    Example:
        curl "http://localhost:8000/clans/clan-uuid-here"
    """
    try:
        result = (
            supabase.table("clans")
            .select("*")
            .eq("id", clan_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch clan: {str(exc)}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=404, detail="Clan not found")

    clan = result.data[0]

    return ClanResponse(
        id=clan["id"],
        clan_name=clan["clan_name"],
        clan_description=clan.get("clan_description"),
        clan_image=clan.get("clan_image"),
        max_members=clan["max_members"],
        clan_leader=clan["clan_leader"],
        clan_members=clan.get("clan_members", []),
        clan_status=clan["clan_status"],
        clan_region=clan.get("clan_region"),
        created_at=clan.get("created_at"),
        updated_at=clan.get("updated_at"),
    )


@router.post("", response_model=ClanResponse, status_code=201)
def create_clan(
    clan_data: ClanCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ClanResponse:
    """
    Create a new clan.

    Example:
        curl -X POST http://localhost:8000/clans \
          -H "Content-Type: application/json" \
          -d '{
            "clan_name": "Crypto Warriors",
            "clan_description": "Elite trading clan",
            "max_members": 50,
            "clan_status": "public",
            "clan_region": "US",
            "clan_leader": "user-uuid-here"
          }'
    """
    # Insert the clan into the database
    try:
        result = (
            supabase.table("clans")
            .insert({
                "clan_name": clan_data.clan_name,
                "clan_description": clan_data.clan_description,
                "clan_image": clan_data.clan_image,
                "max_members": clan_data.max_members,
                "clan_leader": clan_data.clan_leader,
                "clan_members": [clan_data.clan_leader],  # Leader is first member
                "clan_status": clan_data.clan_status,
                "clan_region": clan_data.clan_region,
            })
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create clan: {str(exc)}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create clan")

    clan = result.data[0]

    return ClanResponse(
        id=clan["id"],
        clan_name=clan["clan_name"],
        clan_description=clan.get("clan_description"),
        clan_image=clan.get("clan_image"),
        max_members=clan["max_members"],
        clan_leader=clan["clan_leader"],
        clan_members=clan.get("clan_members", []),
        clan_status=clan["clan_status"],
        clan_region=clan.get("clan_region"),
        created_at=clan.get("created_at"),
        updated_at=clan.get("updated_at"),
    )


@router.patch("/{clan_id}", response_model=ClanResponse)
def update_clan(
    clan_id: str,
    clan_data: ClanUpdate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ClanResponse:
    """
    Update an existing clan.

    Example:
        curl -X PATCH http://localhost:8000/clans/clan-uuid \
          -H "Content-Type: application/json" \
          -d '{
            "clan_name": "Updated Clan Name",
            "clan_description": "Updated description",
            "max_members": 75,
            "clan_status": "public",
            "clan_region": "US",
            "clan_image": "https://example.com/image.png"
          }'
    """
    # First check if clan exists
    try:
        existing = (
            supabase.table("clans")
            .select("id")
            .eq("id", clan_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch clan: {str(exc)}",
        ) from exc

    if not existing.data:
        raise HTTPException(status_code=404, detail="Clan not found")

    # Update the clan
    try:
        result = (
            supabase.table("clans")
            .update({
                "clan_name": clan_data.clan_name,
                "clan_description": clan_data.clan_description,
                "clan_image": clan_data.clan_image,
                "max_members": clan_data.max_members,
                "clan_status": clan_data.clan_status,
                "clan_region": clan_data.clan_region,
            })
            .eq("id", clan_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update clan: {str(exc)}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update clan")

    clan = result.data[0]

    return ClanResponse(
        id=clan["id"],
        clan_name=clan["clan_name"],
        clan_description=clan.get("clan_description"),
        clan_image=clan.get("clan_image"),
        max_members=clan["max_members"],
        clan_leader=clan["clan_leader"],
        clan_members=clan.get("clan_members", []),
        clan_status=clan["clan_status"],
        clan_region=clan.get("clan_region"),
        created_at=clan.get("created_at"),
        updated_at=clan.get("updated_at"),
    )


@router.get("/{clan_id}/members", response_model=ClanMembersResponse)
def get_clan_members(
    clan_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ClanMembersResponse:
    """
    Get all members of a clan with their user details.
    Fetches the clan data and then gets user details for each member.

    Example:
        curl "http://localhost:8000/clans/clan-uuid/members"
    """
    try:
        # First get the clan to get clan_members array and clan_leader
        clan_result = (
            supabase.table("clans")
            .select("clan_members, clan_leader")
            .eq("id", clan_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch clan: {str(exc)}",
        ) from exc

    if not clan_result.data:
        raise HTTPException(status_code=404, detail="Clan not found")

    clan = clan_result.data[0]
    member_ids = clan.get("clan_members", [])
    clan_leader = clan.get("clan_leader")

    if not member_ids:
        return ClanMembersResponse(members=[], count=0)

    try:
        # Fetch all users in the clan_members array
        users_result = (
            supabase.table("users")
            .select("id, username, profile_image, earnings, wallet_address")
            .in_("id", member_ids)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch users: {str(exc)}",
        ) from exc

    users = users_result.data or []

    # Build members list with role information
    members = []
    for user in users:
        members.append(ClanMemberInfo(
            id=user["id"],
            username=user.get("username"),
            profile_image=user.get("profile_image"),
            earnings=user.get("earnings"),
            wallet_address=user.get("wallet_address"),
            role="Leader" if user["id"] == clan_leader else "Member",
        ))

    return ClanMembersResponse(members=members, count=len(members))


@router.get("/{clan_id}/messages", response_model=ClanMessageListResponse)
def get_clan_messages(
    clan_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClanMessageListResponse:
    """
    Get messages for a clan. Only accessible by clan members.

    Example:
        curl "http://localhost:8000/clans/clan-uuid/messages?limit=20"
    """
    # First get messages without sender info
    try:
        result = (
            supabase.table("clan_messages")
            .select("id, clan_id, sender_id, message, created_at")
            .eq("clan_id", clan_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch messages: {exc}",
        ) from exc

    rows = result.data or []
    messages = []
    
    # Fetch sender info for each message
    for row in rows:
        sender_username = None
        sender_avatar = None
        
        # Get sender details from users table
        try:
            sender_result = (
                supabase.table("users")
                .select("username, profile_image, wallet_address")
                .eq("id", row["sender_id"])
                .limit(1)
                .execute()
            )
            if sender_result.data:
                sender_username = sender_result.data[0].get("username")
                sender_avatar = sender_result.data[0].get("profile_image")
                sender_wallet_address = sender_result.data[0].get("wallet_address")
        except Exception as e:
            print(f"Failed to fetch sender {row['sender_id']}: {e}")
        
        messages.append(ClanMessageResponse(
            id=row["id"],
            clan_id=row["clan_id"],
            sender_id=row["sender_id"],
            sender_walletAddress=sender_result.data[0].get("wallet_address") if sender_result.data else None,
            message=row["message"],
            created_at=row["created_at"],
            sender_username=sender_username,
            sender_avatar=sender_avatar,
        ))

    return ClanMessageListResponse(messages=messages, count=len(messages))


@router.post("/{clan_id}/messages", response_model=ClanMessageResponse, status_code=201)
def create_clan_message(
    clan_id: str,
    message_data: ClanMessageCreate,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> ClanMessageResponse:
    """
    Send a message to a clan chat. User must be a clan member.

    Example:
        curl -X POST http://localhost:8000/clans/clan-uuid/messages \
          -H "Content-Type: application/json" \
          -d '{
            "clan_id": "clan-uuid-here",
            "sender_id": "user-uuid-here",
            "message": "Hello clan!"
          }'
    """
    # Verify the clan_id in body matches the path
    if message_data.clan_id != clan_id:
        raise HTTPException(
            status_code=400,
            detail="Clan ID does not match the path",
        )

    # Insert the message
    try:
        result = (
            supabase.table("clan_messages")
            .insert({
                "clan_id": message_data.clan_id,
                "sender_id": message_data.sender_id,
                "message": message_data.message,
            })
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create message: {exc}",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create message")

    # Get sender info
    row = result.data[0]
    sender_result = (
        supabase.table("users")
        .select("username, profile_image, wallet_address")
        .eq("id", message_data.sender_id)
        .limit(1)
        .execute()
    )
    sender_data = sender_result.data[0] if sender_result.data else {}

    return ClanMessageResponse(
        id=row["id"],
        clan_id=row["clan_id"],
        sender_id=row["sender_id"],
        sender_walletAddress=sender_data.get("wallet_address"),
        message=row["message"],
        created_at=row["created_at"],
        sender_username=sender_data.get("username"),
        sender_avatar=sender_data.get("profile_image"),
    )


class JoinClanResponse(BaseModel):
    """Response model for join clan operation."""
    success: bool
    message: str
    members: List[str]


@router.post("/{clan_id}/join", response_model=JoinClanResponse)
def join_clan(
    clan_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
    user_id: str = Query(..., description="User ID to add to the clan"),
) -> JoinClanResponse:
    """
    Join a clan by adding a user to the clan_members array.

    Example:
        curl -X POST "http://localhost:8000/clans/clan-uuid/join?user_id=user-uuid"
    """
    try:
        # First get the clan to check if it exists and get current members
        clan_result = (
            supabase.table("clans")
            .select("clan_members, max_members, clan_status")
            .eq("id", clan_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch clan: {str(exc)}",
        ) from exc

    if not clan_result.data:
        raise HTTPException(status_code=404, detail="Clan not found")

    clan = clan_result.data[0]
    current_members = clan.get("clan_members", [])
    max_members = clan["max_members"]
    clan_status = clan["clan_status"]

    # Check if clan is public
    if clan_status != "public":
        raise HTTPException(status_code=403, detail="This clan is invite-only")

    # Check if clan is full
    if len(current_members) >= max_members:
        raise HTTPException(status_code=400, detail="Clan is full")

    # Check if user is already a member
    if user_id in current_members:
        raise HTTPException(status_code=400, detail="User is already a member of this clan")

    # Add user to clan_members
    updated_members = current_members + [user_id]

    try:
        update_result = (
            supabase.table("clans")
            .update({"clan_members": updated_members})
            .eq("id", clan_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update clan members: {str(exc)}",
        ) from exc

    if not update_result.data:
        raise HTTPException(status_code=500, detail="Failed to join clan")

    return JoinClanResponse(
        success=True,
        message="Successfully joined clan",
        members=updated_members,
    )


@router.post("/{clan_id}/leave", response_model=JoinClanResponse)
def leave_clan(
    clan_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
    user_id: str = Query(..., description="User ID to remove from the clan"),
) -> JoinClanResponse:
    """
    Leave a clan by removing a user from the clan_members array.

    Example:
        curl -X POST "http://localhost:8000/clans/clan-uuid/leave?user_id=user-uuid"
    """
    try:
        # First get the clan to check if it exists and get current members
        clan_result = (
            supabase.table("clans")
            .select("clan_members, clan_leader")
            .eq("id", clan_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch clan: {str(exc)}",
        ) from exc

    if not clan_result.data:
        raise HTTPException(status_code=404, detail="Clan not found")

    clan = clan_result.data[0]
    current_members = clan.get("clan_members", [])
    clan_leader = clan.get("clan_leader")

    # Check if user is a member
    if user_id not in current_members:
        raise HTTPException(status_code=400, detail="User is not a member of this clan")

    # Check if user is the leader - they cannot leave without transferring leadership
    if user_id == clan_leader:
        raise HTTPException(
            status_code=400,
            detail="Leader cannot leave the clan. Please transfer leadership first or disband the clan.",
        )

    # Remove user from clan_members
    updated_members = [m for m in current_members if m != user_id]

    try:
        update_result = (
            supabase.table("clans")
            .update({"clan_members": updated_members})
            .eq("id", clan_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update clan members: {str(exc)}",
        ) from exc

    if not update_result.data:
        raise HTTPException(status_code=500, detail="Failed to leave clan")

    return JoinClanResponse(
        success=True,
        message="Successfully left clan",
        members=updated_members,
    )


@router.delete("/{clan_id}/messages/{message_id}", status_code=204)
def delete_clan_message(
    clan_id: str,
    message_id: str,
    supabase: Annotated[Client, Depends(get_supabase)],
) -> None:
    """
    Delete a message. User must be the sender.

    Example:
        curl -X DELETE http://localhost:8000/clans/clan-uuid/messages/message-uuid-here
    """
    try:
        supabase.table("clan_messages").delete().eq("id", message_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete message: {exc}",
        ) from exc
