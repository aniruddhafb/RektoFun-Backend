"""Public reads and restricted writes for site-wide operational controls."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from services.database import get_service_db_client as get_db_client

router = APIRouter(tags=["site-settings"])

SETTINGS_ID = "global"


class SiteSettingsPatch(BaseModel):
    site_maintenance: Optional[bool] = None
    crypto_creation_locked: Optional[bool] = None
    sports_creation_locked: Optional[bool] = None
    price_challenges_locked: Optional[bool] = None
    statement_challenges_locked: Optional[bool] = None
    pvp_challenges_locked: Optional[bool] = None
    team_challenges_locked: Optional[bool] = None


def _get_settings(db: Client) -> dict:
    result = (
        db.table("site_settings")
        .select("*")
        .eq("id", SETTINGS_ID)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=503,
            detail="Site settings are not initialized. Run the site_settings migration.",
        )
    return result.data[0]


@router.get("/site-settings")
async def get_site_settings(db: Client = Depends(get_db_client)):
    return _get_settings(db)


@router.patch("/admin/site-settings")
async def update_site_settings(
    payload: SiteSettingsPatch,
    db: Client = Depends(get_db_client),
):
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        return _get_settings(db)
    result = (
        db.table("site_settings")
        .update(patch)
        .eq("id", SETTINGS_ID)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Site settings row not found")
    return result.data[0]
