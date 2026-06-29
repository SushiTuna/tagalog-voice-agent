import logging
import os
import re
import time
from typing import Any

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMContextFrame, EndFrame, TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.cartesia.stt import CartesiaSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.qwen.llm import QwenLLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.transcriptions.language import Language

from bot_config import OPENING_GREETING, PRODUCTS
from prompt_builder import build_system_prompt
from tools import build_capture_lead_tool, build_confirm_contact_info_tool
from transcript import TranscriptCollector
from webhooks import send_post_call_webhook, send_lead_capture_webhook

logger = logging.getLogger(__name__)

# ── Fallback lead-capture helpers ──────────────────────────────────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?63|0)?\s*\d{3}[\s\-]?\d{3}[\s\-]?\d{4}")
_NAME_PATTERNS = [
    re.compile(r"(?:my name is|i am|i'm|call me)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", re.IGNORECASE),
    re.compile(r"(?:name is|it's)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", re.IGNORECASE),
]


def _extract_contact_info(transcript: list[dict[str, str]]) -> dict[str, str]:
    """Scan user utterances for name, email, and phone number."""
    result: dict[str, str] = {}
    for entry in transcript:
        if entry.get("role") != "user":
            continue
        text = entry.get("text", "")

        if "email" not in result:
            email_match = _EMAIL_RE.search(text)
            if email_match:
                result["email"] = email_match.group(0).strip()

        if "phone" not in result:
            phone_match = _PHONE_RE.search(text)
            if phone_match:
                result["phone"] = phone_match.group(0).strip()

        if "name" not in result:
            for pat in _NAME_PATTERNS:
                name_match = pat.search(text)
                if name_match:
                    result["name"] = name_match.group(1).strip()
                    break

    return result


def _detect_product_interest(
    transcript: list[dict[str, str]],
    products_discussed: set[str],
) -> str | None:
    """Return the product the user most clearly expressed interest in."""
    user_texts = [
        entry.get("text", "").lower()
        for entry in transcript
        if entry.get("role") == "user"
    ]
    combined = " ".join(user_texts)

    for product in PRODUCTS:
        if product["name"] in products_discussed:
            if any(kw in combined for kw in product["keywords"]):
                return product["display_name"]

    return None


def _lead_already_captured(transcript: list[dict[str, str]]) -> bool:
    """Check if the LLM already fired capture_lead or confirm_contact_info during the call."""
    for entry in transcript:
        if entry.get("role") == "assistant":
            text = entry.get("text", "").lower()
            if "lead_captured" in text or "capture_lead" in text or "confirm_contact_info" in text:
                return True
    return False


async def create_and_run_bot(
    room_url: str,
    session_id: str,
    caller_info: dict[str, str] | None = None,
    product_focus: str | None = None,
) -> None:
    """Create the pipeline and run the bot for a single call session.

    Args:
        room_url: The Daily room URL to join.
        session_id: A unique identifier for this call session.
        caller_info: Optional caller details (name, email, phone).
        product_focus: Optional product to prioritize in the conversation.
    """
    transport = DailyTransport(
        room_url,
        None,
        "Taglish AI Bot",
        DailyParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
        ),
    )

    stt = CartesiaSTTService(
        api_key=os.environ["CARTESIA_API_KEY"],
    )

    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTTSService.Settings(
            voice=os.environ["CARTESIA_VOICE_ID"],
            model="sonic-3.5",
            language=Language.TL,
        ),
    )

    llm = QwenLLMService(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        model="qwen-max",
    )

    system_prompt = build_system_prompt(product_focus, caller_info)
    confirm_tool, get_confirmed = build_confirm_contact_info_tool(session_id)
    capture_tool = build_capture_lead_tool(session_id)
    tools = ToolsSchema(standard_tools=[confirm_tool, capture_tool])

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]

    context = LLMContext(messages, tools=tools)
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    collector = TranscriptCollector()

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            collector,
            tts,
            context_aggregator.assistant(),
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    call_start_time = time.time()

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        logger.info(
            "Participant joined: %s (session %s)",
            participant.get("id", "unknown"),
            session_id,
        )
        await task.queue_frames([LLMContextFrame(context=context)])
        await task.queue_frames([TextFrame(OPENING_GREETING)])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        duration = time.time() - call_start_time
        logger.info(
            "Participant left (session %s). Duration: %.1fs. Transcript entries: %d",
            session_id,
            duration,
            len(collector.transcript),
        )

        transcript = collector.transcript

        # --- Deterministic fallback: capture lead if LLM didn't ---
        if not _lead_already_captured(transcript):
            # First check if confirm_contact_info stored verified details
            confirmed = get_confirmed()
            if confirmed:
                logger.info(
                    "Fallback lead capture (from confirmed info): %s <%s> interested in %s",
                    confirmed["name"],
                    confirmed["email"],
                    confirmed["product_interest"],
                )
                await send_lead_capture_webhook(
                    name=confirmed["name"],
                    email=confirmed["email"],
                    product_interest=confirmed["product_interest"],
                    session_id=session_id,
                )
            else:
                contact = _extract_contact_info(transcript)
                product_interest = _detect_product_interest(
                    transcript, collector.products_discussed
                )
                if contact.get("name") and contact.get("email") and product_interest:
                    logger.info(
                        "Fallback lead capture (from transcript): %s <%s> interested in %s",
                        contact["name"],
                        contact["email"],
                        product_interest,
                    )
                    await send_lead_capture_webhook(
                        name=contact["name"],
                        email=contact["email"],
                        product_interest=product_interest,
                        session_id=session_id,
                    )

        lead_status = "captured" if _lead_already_captured(transcript) else "not_captured"

        await send_post_call_webhook(
            transcript=transcript,
            products_discussed=sorted(collector.products_discussed),
            lead_status=lead_status,
            duration_seconds=duration,
            session_id=session_id,
            room_url=room_url,
        )

        # Terminate the pipeline so the bot exits cleanly
        await task.queue_frame(EndFrame())

    runner = PipelineRunner()
    await runner.run(task)
