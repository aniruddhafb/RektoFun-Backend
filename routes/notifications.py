from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from models.notification import NotificationListResponse, NotificationReadRequest
from services.database import get_db_client
from services.notification_service import get_notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(wallet_address: str, limit: int = Query(50, ge=1, le=100), db: Client = Depends(get_db_client)):
    try:
        return await get_notification_service(db).list_for_wallet(wallet_address, limit)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.patch("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(body: NotificationReadRequest, db: Client = Depends(get_db_client)):
    await get_notification_service(db).mark_read(body.wallet_address)


@router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_one(notification_id: int, body: NotificationReadRequest, db: Client = Depends(get_db_client)):
    await get_notification_service(db).mark_read(body.wallet_address, notification_id)
