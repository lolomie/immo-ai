import json
import os
from typing import Generator

import anthropic

from .config import CLAUDE_MODEL, PROMPTS_DIR
from .models import PropertyInput


def _build_prompt(property_data: PropertyInput) -> tuple[str, str]:
    template_path = os.path.join(PROMPTS_DIR, "generation.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    data_for_llm = property_data.model_dump(exclude={"notes"})
    property_json = json.dumps(data_for_llm, ensure_ascii=False, indent=2)

    parts = template.split("{property_json}", 1)
    system_text = parts[0].strip()
    user_text = property_json + (parts[1] if len(parts) > 1 else "")
    return system_text, user_text.strip()


def generate_expose(property_data: PropertyInput) -> str:
    system_text, user_text = _build_prompt(property_data)
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    )
    return message.content[0].text.strip()


def stream_expose(property_data: PropertyInput) -> Generator[str, None, None]:
    system_text, user_text = _build_prompt(property_data)
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        for text in stream.text_stream:
            yield text
