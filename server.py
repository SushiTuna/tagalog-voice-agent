import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from pipeline import create_and_run_bot

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DAILY_API_URL = "https://api.daily.co/v1"

# Track active sessions so we can report status and prevent duplicates
active_sessions: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Voice agent server starting up")
    yield
    logger.info("Voice agent server shutting down — active sessions: %d", len(active_sessions))


app = FastAPI(
    title="Taglish AI Voice Agent",
    description="API-driven voice agent for insurance lead engagement. Trigger calls, capture leads, and receive post-call webhooks.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Request / Response Models ──────────────────────────────────────────────


class CallerInfo(BaseModel):
    name: str = Field(default="", description="Caller's name")
    email: str = Field(default="", description="Caller's email")
    phone: str = Field(default="", description="Caller's phone number")


class RoomConfig(BaseModel):
    name: str = Field(default="", description="Custom room name (auto-generated if empty)")
    max_participants: int = Field(default=2, description="Max participants allowed in the room")
    expire_in_secs: int = Field(default=3600, description="Room expiry in seconds")


class StartCallRequest(BaseModel):
    caller_info: CallerInfo | None = Field(default=None, description="Caller details to pass to the bot")
    product_focus: str | None = Field(
        default=None,
        description="Product to prioritize: WanderSafe, GadgetShield Plus, IncomeGuard, FurParent Vet Care",
    )
    room_config: RoomConfig | None = Field(default=None, description="Daily room creation options")


class StartCallResponse(BaseModel):
    session_id: str
    room_url: str
    room_name: str
    status: str


class LeadCaptureRequest(BaseModel):
    name: str
    email: str
    product_interest: str
    session_id: str = ""


# ── Daily Room Creation ─────────────────────────────────────────────────────


async def create_daily_room(config: RoomConfig | None = None) -> dict[str, str]:
    """Create a Daily room via the REST API. Returns {"url": ..., "name": ...}."""
    api_key = os.environ.get("DAILY_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="DAILY_API_KEY is not configured. Cannot auto-create rooms.",
        )

    room_name = ""
    if config and config.name:
        room_name = config.name
    else:
        room_name = f"voice-agent-{uuid.uuid4().hex[:8]}"

    body: dict = {
        "name": room_name,
        "properties": {
            "max_participants": config.max_participants if config else 2,
            "exp": int(time.time()) + (config.expire_in_secs if config else 3600),
        },
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{DAILY_API_URL}/rooms", json=body, headers=headers)
        if resp.status_code != 200:
            logger.error("Daily room creation failed: %d %s", resp.status_code, resp.text)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to create Daily room: {resp.status_code} {resp.text}",
            )
        data = resp.json()

    return {"url": data["url"], "name": data["name"]}


# ── Bot Session Runner ───────────────────────────────────────────────────────


async def run_bot_session(
    session_id: str,
    room_url: str,
    caller_info: dict | None,
    product_focus: str | None,
) -> None:
    """Run the bot for a single session. Cleans up on completion."""
    try:
        await create_and_run_bot(
            room_url=room_url,
            session_id=session_id,
            caller_info=caller_info,
            product_focus=product_focus,
        )
    except Exception as exc:
        logger.error("Bot session %s failed: %s", session_id, exc)
    finally:
        session = active_sessions.get(session_id)
        if session:
            session["status"] = "completed"
            logger.info("Session %s completed", session_id)


# ── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_sessions": len(active_sessions),
        "webhook_configured": bool(os.environ.get("WEBHOOK_URL")),
    }


@app.post("/start-call", response_model=StartCallResponse)
async def start_call(req: StartCallRequest):
    """Trigger a new voice agent call session.

    Auto-creates a Daily room, launches the bot, and returns the room URL.
    Use this endpoint from Zapier, n8n, make.com, or any automation platform.
    """
    room = await create_daily_room(req.room_config)

    session_id = uuid.uuid4().hex[:12]
    caller_info = req.caller_info.model_dump() if req.caller_info else None

    active_sessions[session_id] = {
        "status": "running",
        "room_url": room["url"],
        "room_name": room["name"],
        "caller_info": caller_info,
        "product_focus": req.product_focus,
    }

    asyncio.create_task(
        run_bot_session(session_id, room["url"], caller_info, req.product_focus)
    )

    logger.info("Started session %s in room %s", session_id, room["name"])

    return StartCallResponse(
        session_id=session_id,
        room_url=room["url"],
        room_name=room["name"],
        status="started",
    )


@app.post("/lead-capture")
async def manual_lead_capture(req: LeadCaptureRequest):
    """Manually trigger a lead capture webhook.

    Use this when the LLM tool didn't fire but you have lead data from another source.
    """
    from webhooks import send_lead_capture_webhook

    success = await send_lead_capture_webhook(
        name=req.name,
        email=req.email,
        product_interest=req.product_interest,
        session_id=req.session_id,
    )
    if not success:
        raise HTTPException(
            status_code=502,
            detail="Failed to send lead capture webhook. Check WEBHOOK_URL configuration.",
        )
    return {"status": "lead_sent", "name": req.name, "email": req.email}


@app.get("/sessions")
async def list_sessions():
    """List all sessions (active and completed since server start)."""
    return {"sessions": active_sessions}
