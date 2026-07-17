"""Restricted operational endpoints used by the RektoFun admin panel."""

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from uuid import uuid4
from pydantic import BaseModel
from supabase import Client

from services.database import get_service_db_client as get_db_client

router = APIRouter(prefix="/admin", tags=["admin"])
class RoleUpdate(BaseModel):
    user_type: Literal["user", "moderator"]


class RedemptionStatusUpdate(BaseModel):
    status: Literal["pending", "paid", "rejected"]


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    payload: RoleUpdate,
    db: Client = Depends(get_db_client),
):
    result = db.table("user").update({"user_type": payload.user_type}).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    return result.data[0]


@router.get("/referrals")
async def list_referrals(
    db: Client = Depends(get_db_client),
):
    users = db.table("user").select(
        "id,username,pubkey,referral_code,referred_by,referrals,earnings"
    ).order("created_at", desc=True).execute().data or []
    redemptions = db.table("referral_redemption_requests").select(
        "id,user_id,amount,status,requested_at"
    ).order("requested_at", desc=True).execute().data or []
    user_by_id = {str(user["id"]): user for user in users}
    for redemption in redemptions:
        user = user_by_id.get(str(redemption.get("user_id")))
        redemption["username"] = user.get("username") if user else None
        redemption["wallet_address"] = user.get("pubkey") if user else None
    return {"users": users, "redemptions": redemptions}


@router.patch("/referrals/redemptions/{redemption_id}")
async def update_redemption_status(
    redemption_id: int,
    payload: RedemptionStatusUpdate,
    db: Client = Depends(get_db_client),
):
    result = db.table("referral_redemption_requests").update(
        {"status": payload.status}
    ).eq("id", redemption_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Redemption request not found")
    return result.data[0]


@router.post("/category-image")
async def upload_category_image(
    image: UploadFile = File(...),
    db: Client = Depends(get_db_client),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file")
    content = await image.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be smaller than 5 MB")
    extension = (image.filename or "image.png").rsplit(".", 1)[-1].lower()
    path = f"categories/{uuid4().hex}.{extension}"
    bucket = "category-images"
    try:
        db.storage.from_(bucket).upload(path, content, {"content-type": image.content_type, "upsert": "false"})
    except Exception as exc:
        if "bucket" in str(exc).lower() and "not found" in str(exc).lower():
            db.storage.create_bucket(bucket, options={"public": True})
            db.storage.from_(bucket).upload(path, content, {"content-type": image.content_type, "upsert": "false"})
        else:
            raise HTTPException(status_code=500, detail="Category image upload failed") from exc
    return {"url": db.storage.from_(bucket).get_public_url(path)}
