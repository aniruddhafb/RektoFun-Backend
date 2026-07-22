"""Best-effort Telegram alerts for newly created challenges."""

import html
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from models.challenge import ChallengeResponse

logger = logging.getLogger(__name__)


def _display_value(value: object, fallback: str = "N/A") -> str:
    """Return an HTML-safe display value, including values backed by enums."""
    if value is None or value == "":
        return fallback
    raw_value = getattr(value, "value", value)
    return html.escape(str(raw_value))


def _parse_datetime(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _relative_duration(future: datetime, now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    seconds = int((future.astimezone(timezone.utc) - current.astimezone(timezone.utc)).total_seconds())
    if seconds <= 0:
        return "now"

    total_minutes = max(1, (seconds + 30) // 60)
    days, remainder = divmod(total_minutes, 1_440)
    hours, minutes = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if not days and minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " ".join(parts[:2])


def _format_target(value: object) -> Optional[str]:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return None


def _resolution_time(challenge: ChallengeResponse) -> Optional[datetime]:
    metadata = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    composer = metadata.get("composer") if isinstance(metadata.get("composer"), dict) else {}
    return _parse_datetime(composer.get("resolves_at"))


def _challenge_title(challenge: ChallengeResponse) -> str:
    target = _format_target(challenge.target)
    resolves_at = _resolution_time(challenge)
    direction = str(getattr(challenge.direction, "value", challenge.direction) or "").upper()
    direction_label = {"UP": "above", "DOWN": "below"}.get(direction)

    if challenge.ticker and direction_label and target and resolves_at:
        date_label = f"{resolves_at.day} {resolves_at.strftime('%B')}"
        return f"{challenge.ticker.upper()} {direction_label} {target} by {date_label}"
    return challenge.statement or "A new challenge is live"


def build_new_challenge_message(
    challenge: ChallengeResponse,
    creator_username: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
) -> tuple[str, Optional[str]]:
    """Build the Telegram message and optional frontend deep link."""
    frontend_url = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    challenge_url = None
    if frontend_url:
        challenge_url = f"{frontend_url}/challenges?{urlencode({'challengeId': challenge.id})}"

    lines = [
        "⚔️ <b>New RektoFun Challenge</b>",
        "",
        f"<b>{_display_value(_challenge_title(challenge))}</b>",
        "",
        f"Creator: {_display_value(creator_username, 'Unknown')}",
        f"Asset: {_display_value(challenge.ticker)}",
        f"Mode: {_display_value(challenge.mode)}",
        f"Initial bet: {_display_value(challenge.initial_bet, '0')} USDC",
    ]
    if challenge.expiry:
        lines.append(f"Expires in: {_relative_duration(challenge.expiry, now)}")

    return "\n".join(lines), challenge_url


async def send_new_challenge_alert(
    challenge: ChallengeResponse, creator_username: Optional[str] = None
) -> bool:
    """Send an alert without allowing Telegram failures to fail challenge creation."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        logger.warning(
            "Telegram challenge alerts are disabled because TELEGRAM_BOT_TOKEN or "
            "TELEGRAM_CHAT_ID is not configured"
        )
        return False

    text, challenge_url = build_new_challenge_message(challenge, creator_username)
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    if challenge_url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "View challenge →", "url": challenge_url}]]
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
        logger.info("Sent Telegram alert for challenge %s", challenge.id)
        return True
    except Exception as error:
        logger.error(
            "Failed to send Telegram alert for challenge %s: %s",
            challenge.id,
            error,
        )
        return False
