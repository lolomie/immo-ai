import json
import logging
import os
import re

from .config import LLM_PROVIDER, PROMPTS_DIR
from .models import PropertyInput

logger = logging.getLogger(__name__)


def validate_expose_with_claude(property_data: PropertyInput, expose_text: str) -> dict:
    """
    Always use Claude for validation regardless of LLM_PROVIDER.
    This is the quality gate for the automation pipeline.
    """
    system_text, user_text = _build_validation_prompt(property_data, expose_text)
    raw = _call_anthropic(system_text, user_text)
    return _parse_validation(raw)


def _build_validation_prompt(property_data: PropertyInput, expose_text: str) -> tuple[str, str]:
    import json as _json
    template_path = os.path.join(PROMPTS_DIR, "validation.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    data_for_llm = property_data.model_dump(exclude={"notes"})
    property_json = _json.dumps(data_for_llm, ensure_ascii=False, indent=2)
    parts = template.split("{property_json}", 1)
    system_text = parts[0].strip()
    user_text = (property_json + parts[1].replace("{expose_text}", expose_text)).strip() if len(parts) > 1 else template
    return system_text, user_text


def validate_expose(property_data: PropertyInput, expose_text: str) -> dict:
    system_text, user_text = _build_validation_prompt(property_data, expose_text)

    if LLM_PROVIDER == "groq":
        raw = _call_groq(system_text, user_text)
    else:
        raw = _call_anthropic(system_text, user_text)

    return _parse_validation(raw)


def _call_anthropic(system_text: str, user_text: str) -> str:
    import anthropic
    from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    )
    return message.content[0].text.strip()


def _call_groq(system_text: str, user_text: str) -> str:
    from groq import Groq
    from .config import GROQ_API_KEY, GROQ_MODEL
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=512,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
    )
    return response.choices[0].message.content.strip()


def _parse_validation(raw: str) -> dict:
    try:
        return _extract(json.loads(raw))
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if match:
        try:
            return _extract(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]+?\}", raw)
    if match:
        try:
            return _extract(json.loads(match.group(0)))
        except json.JSONDecodeError:
            pass
    logger.warning("Validation JSON parse failed, raw: %s", raw[:200])
    return {"hallucinated": True, "details": f"Validierung fehlgeschlagen (kein JSON): {raw[:200]}"}


def _extract(result: dict) -> dict:
    return {
        "hallucinated": bool(result.get("hallucinated", False)),
        "details": str(result.get("details", "")),
    }
