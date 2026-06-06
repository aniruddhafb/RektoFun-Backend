import random
import string
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from config import get_supabase
from services.email_service import send_otp_email

router = APIRouter(prefix="/email", tags=["email subscription"])

class OTPRequest(BaseModel):
    email: EmailStr

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str

@router.post("/request-otp")
async def request_otp(request: OTPRequest):
    email = request.email.lower()
    supabase = get_supabase()

    # Generate 6-digit OTP
    otp = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    # Store OTP in Supabase
    try:
        # Use upsert to overwrite any existing OTP for this email
        supabase.table("email_otps").upsert({
            "email": email,
            "otp": otp,
            "expires_at": expires_at.isoformat()
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Send email
    sent = await send_otp_email(email, otp)
    if not sent:
        raise HTTPException(status_code=500, detail="Failed to send verification email")

    return {"message": "Verification code sent to your email"}

@router.post("/verify-otp")
async def verify_otp(request: OTPVerify):
    email = request.email.lower()
    otp = request.otp
    supabase = get_supabase()

    # Check OTP
    try:
        response = supabase.table("email_otps").select("*").eq("email", email).single().execute()
    except Exception:
        raise HTTPException(status_code=400, detail="No OTP requested for this email")
    
    if not response.data:
        raise HTTPException(status_code=400, detail="No OTP requested for this email")

    data = response.data
    stored_otp = data.get("otp")
    expires_at_str = data.get("expires_at")
    
    if not expires_at_str:
        raise HTTPException(status_code=500, detail="OTP expiration time missing in database")

    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
    except Exception as e:
        print(f"Date parsing error: {e}")
        raise HTTPException(status_code=500, detail="Error processing expiration date")

    if otp != stored_otp:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Verification code has expired")

    # Mark email as verified
    try:
        verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Check if user already exists in the emails table
        user_check = supabase.table("emails").select("id").eq("email", email).execute()
        
        if user_check.data and len(user_check.data) > 0:
            # Update existing user
            user_id = user_check.data[0]["id"]
            supabase.table("emails").update({
                "is_verified": True,
                "verified_at": verified_at
            }).eq("id", user_id).execute()
        else:
            # Insert new user
            supabase.table("emails").insert({
                "email": email,
                "is_verified": True,
                "verified_at": verified_at
            }).execute()

        # Delete OTP after successful verification
        supabase.table("email_otps").delete().eq("email", email).execute()
    except Exception as e:
        print(f"CRITICAL DATABASE ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return {"message": "Email successfully verified and subscribed"}