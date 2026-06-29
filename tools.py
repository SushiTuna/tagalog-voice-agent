import logging

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

from bot_config import PRODUCTS
from webhooks import send_lead_capture_webhook

logger = logging.getLogger(__name__)


def build_confirm_contact_info_tool(session_id: str) -> tuple[FunctionSchema, callable]:
    """Build the confirm_contact_info tool schema.

    Returns:
        A tuple of (FunctionSchema, get_confirmed_info_callable).
    """
    # Shared storage for confirmed contact info between tool calls in the same session
    _confirmed_info: dict = {}

    async def handle_confirm_contact_info(params: FunctionCallParams):
        """Confirm the caller's contact details before capturing the lead."""
        args = params.arguments
        name = args.get("name", "")
        email = args.get("email", "")
        phone = args.get("phone", "")
        product_interest = args.get("product_interest", "")

        # Spell out email for TTS
        spelled_email = " dot ".join(
            "-".join(part) for part in email.replace(" ", "").replace("@", " at ").split(".")
        ).replace(" at ", " at ")
        phone_note = f" at phone number {phone}" if phone else ""
        confirmation = (
            f"Got it. Let me confirm your details, {name}. "
            f"Your email is {spelled_email}{phone_note}, "
            f"and you're interested in {product_interest}. "
            f"Tama ba yan? Just say yes if that's correct."
        )

        logger.info(
            "Contact info confirmed: %s <%s> %s interested in %s",
            name,
            email,
            phone or "(no phone)",
            product_interest,
        )
        _confirmed_info.update({
            "name": name,
            "email": email,
            "phone": phone,
            "product_interest": product_interest,
            "confirmed": True,
        })
        await params.result_callback({
            "status": "contact_confirmed",
            "message": confirmation,
        })

    def get_confirmed_info() -> dict | None:
        """Return the confirmed contact info if available, else None."""
        if _confirmed_info.get("confirmed"):
            return _confirmed_info.copy()
        return None

    return FunctionSchema(
        name="confirm_contact_info",
        description="Confirm the caller's contact details before capturing the lead. Read back the email character by character and ask the caller to confirm. Call this BEFORE capture_lead.",
        properties={
            "name": {
                "type": "string",
                "description": "The caller's full name.",
            },
            "email": {
                "type": "string",
                "description": "The caller's email address. Spell it out character by character when reading back.",
            },
            "phone": {
                "type": "string",
                "description": "The caller's phone or mobile number (optional).",
            },
            "product_interest": {
                "type": "string",
                "description": "The insurance product the caller is interested in.",
                "enum": [p["display_name"] for p in PRODUCTS],
            },
        },
        required=["name", "email", "product_interest"],
        handler=handle_confirm_contact_info,
    ), get_confirmed_info


def build_capture_lead_tool(session_id: str) -> FunctionSchema:
    """Build the capture_lead tool schema with a handler that fires the webhook."""

    async def handle_capture_lead(params: FunctionCallParams):
        """Capture a lead when the caller expresses interest and shares contact info."""
        args = params.arguments
        name = args.get("name", "")
        email = args.get("email", "")
        product_interest = args.get("product_interest", "")

        logger.info("Lead captured: %s <%s> interested in %s", name, email, product_interest)
        await send_lead_capture_webhook(
            name=name,
            email=email,
            product_interest=product_interest,
            session_id=session_id,
        )
        await params.result_callback({
            "status": "lead_captured",
            "message": f"Lead {name} captured successfully. Continue the conversation naturally.",
        })

    return FunctionSchema(
        name="capture_lead",
        description="Capture a confirmed lead. Only call this AFTER confirm_contact_info has been called and the caller has verified their details.",
        properties={
            "name": {
                "type": "string",
                "description": "The caller's full name (must match what was confirmed).",
            },
            "email": {
                "type": "string",
                "description": "The caller's email address (must match what was confirmed).",
            },
            "product_interest": {
                "type": "string",
                "description": "The insurance product the caller is interested in.",
                "enum": [p["display_name"] for p in PRODUCTS],
            },
        },
        required=["name", "email", "product_interest"],
        handler=handle_capture_lead,
    )
