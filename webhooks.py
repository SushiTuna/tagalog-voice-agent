import os
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
WEBHOOK_TIMEOUT = 15  # seconds
WEBHOOK_RETRIES = 2


async def _post_json(url: str, payload: dict[str, Any], retries: int = WEBHOOK_RETRIES) -> bool:
    """POST JSON to a webhook URL with retry logic. Returns True on success."""
    if not url:
        logger.warning("WEBHOOK_URL is not set; skipping webhook call")
        return False

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Webhook sent successfully (attempt %d, status %d)", attempt, resp.status_code)
                return True
        except httpx.HTTPError as exc:
            logger.warning("Webhook attempt %d failed: %s", attempt, exc)
            if attempt == retries:
                logger.error("Webhook failed after %d attempts", retries)
                return False

    return False


async def send_post_call_webhook(
    transcript: list[dict[str, str]],
    products_discussed: list[str],
    lead_status: str,
    duration_seconds: float,
    session_id: str,
    room_url: str,
) -> bool:
    """Send a post-call summary to the configured WEBHOOK_URL."""
    payload = {
        "event": "call_ended",
        "session_id": session_id,
        "room_url": room_url,
        "duration_seconds": round(duration_seconds, 1),
        "transcript": transcript,
        "products_discussed": products_discussed,
        "lead_status": lead_status,
    }
    return await _post_json(WEBHOOK_URL, payload)


async def send_lead_capture_webhook(
    name: str,
    email: str,
    product_interest: str,
    session_id: str = "",
) -> bool:
    """Send a lead capture event to the configured WEBHOOK_URL."""
    payload = {
        "event": "lead_captured",
        "session_id": session_id,
        "name": name,
        "email": email,
        "product_interest": product_interest,
    }
    return await _post_json(WEBHOOK_URL, payload)
