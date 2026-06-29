import json
from pathlib import Path

_prompts_path = Path(__file__).parent / "prompts.json"
with open(_prompts_path, "r") as _f:
    _prompts = json.load(_f)

OPENING_GREETING = _prompts["opening_greeting"].strip()
SYSTEM_PROMPT = _prompts["system_prompt"].strip()
PRODUCTS = _prompts["products"]
