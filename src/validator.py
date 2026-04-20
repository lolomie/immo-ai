import json
import logging
import os
import re

import anthropic

from .config import CLAUDE_MODEL, PROMPTS_DIR
from .models import PropertyInput

logger = logging.getLogger(__name__)


def validate_expose(property_data: PropertyInput, expose_text: str) -> dict:
    template_path = os.path.join(PROMPTS_DIR, "validation.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    data_for_llm = property_data.model_dump(exclude={"notes"})
    property_json = json.dumps(data_for_llm, ensure_ascii=False, indent=2)

    # Cache the static instruction part, dynamic data goes in user message
    parts = template.split("{property_json}", 1)
    system_text = parts[0].strip()
    user_text = property_json + parts[1].replace("{expose_text}", expose_text) if len(parts) > 1 else template

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text.strip()}],
    )

    raw = message.content[0].text.strip()
    return _parse_validation(raw)


def _parse_validation(raw: str) -> dict:
    # Try 1: direct JSON parse
    try:
        result = json.loads(raw)
        return _extract(result)
    except json.JSONDecodeError:
        pass

    # Try 2: extract from code block
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if match:
        try:
            result = json.loads(match.group(1))
            return _extract(result)
        except json.JSONDecodeError:
            pass

    # Try 3: extract first {...} block
    match = re.search(r"\{[\s\S]+?\}", raw)
    if match:
        try:
            result = json.loads(match.group(0))
            return _extract(result)
        except json.JSONDecodeError:
            pass

    logger.warning("Validation JSON parse failed, raw: %s", raw[:200])
    return {"hallucinated": True, "details": f"Validierung fehlgeschlagen (kein gültiges JSON): {raw[:200]}"}


def _extract(result: dict) -> dict:
    return {
        "hallucinated": bool(result.get("hallucinated", False)),
        "details": str(result.get("details", "")),
    }
