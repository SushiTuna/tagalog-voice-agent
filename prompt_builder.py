from bot_config import SYSTEM_PROMPT


def build_system_prompt(
    product_focus: str | None = None, caller_info: dict | None = None
) -> str:
    """Build the system prompt, optionally injecting caller context."""
    prompt = SYSTEM_PROMPT
    if caller_info:
        caller_line = (
            f"\n\nCaller info available to you: {caller_info}. "
            "Use their name naturally in conversation."
        )
        prompt += caller_line
    if product_focus:
        prompt += (
            f"\n\nThe caller has expressed initial interest in: {product_focus}. "
            "Prioritize this product in your introduction but still cover the others briefly."
        )
    return prompt
