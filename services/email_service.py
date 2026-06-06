import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
from config import get_settings

async def send_otp_email(to_email: str, otp: str):
    settings = get_settings()
    
    if not settings.smtp_user or not settings.smtp_password:
        print("Email credentials missing in environment. Actual email send skipped.")
        print(f"DEBUG: OTP for {to_email} is {otp}")
        return False

    # Run the blocking smtplib call in a thread pool
    def _send():
        try:
            msg = MIMEMultipart()
            msg['From'] = settings.email_from or settings.smtp_user
            msg['To'] = to_email
            msg['Subject'] = "Verify Your Rekto Beta Access"

            body = f"Your verification code for Rekto Beta is: {otp}\n\nThis code will expire in 10 minutes."
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    return await asyncio.to_thread(_send)