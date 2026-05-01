"""Clan chat API endpoints."""

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from config import get_supabase
from models.clan import (
    ClanCreate,
    ClanMessageCreate,
    ClanMessageListResponse,
    ClanMessageResponse,
    ClanResponse,
    coerce_clan_message,
)

router = APIRouter(prefix="/clans", tags=["clans"])


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
    # Get messages with sender info (username and profile_image)
    try:
        result = (
            supabase.table("clan_messages")
            .select("""
                id,
                clan_id,
                sender_id,
                message,
                created_at,
                sender:users!sender_id (
                    username,
                    profile_image
                )
            """)
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
    for row in rows:
        sender_data = row.pop("sender", None)
        sender_username = sender_data.get("username") if sender_data else None
        sender_avatar = sender_data.get("profile_image") if sender_data else None
        messages.append(ClanMessageResponse(
            id=row["id"],
            clan_id=row["clan_id"],
            sender_id=row["sender_id"],
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
        .select("username, profile_image")
        .eq("id", message_data.sender_id)
        .limit(1)
        .execute()
    )
    sender_data = sender_result.data[0] if sender_result.data else {}

    return ClanMessageResponse(
        id=row["id"],
        clan_id=row["clan_id"],
        sender_id=row["sender_id"],
        message=row["message"],
        created_at=row["created_at"],
        sender_username=sender_data.get("username"),
        sender_avatar=sender_data.get("profile_image"),
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
