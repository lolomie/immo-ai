import json
import os
from typing import Generator

from .config import LLM_PROVIDER, PROMPTS_DIR
from .models import PropertyInput


def _load_prompt(property_data: PropertyInput) -> tuple[str, str]:
    template_path = os.path.join(PROMPTS_DIR, "generation.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    data_for_llm = property_data.model_dump(exclude={"notes"})
    property_json = json.dumps(data_for_llm, ensure_ascii=False, indent=2)

    parts = template.split("{property_json}", 1)
    system_text = parts[0].strip()
    user_text = (property_json + parts[1]).strip() if len(parts) > 1 else property_json
    return system_text, user_text


def generate_expose(property_data: PropertyInput) -> str:
    system_text, user_text = _load_prompt(property_data)
    if LLM_PROVIDER == "groq":
        return _generate_groq(system_text, user_text)
    return _generate_anthropic(system_text, user_text)


def stream_expose(property_data: PropertyInput) -> Generator[str, None, None]:
    system_text, user_text = _load_prompt(property_data)
    if LLM_PROVIDER == "groq":
        yield from _stream_groq(system_text, user_text)
    else:
        yield from _stream_anthropic(system_text, user_text)


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _generate_anthropic(system_text: str, user_text: str) -> str:
    import anthropic
    from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    )
    return message.content[0].text.strip()


def _stream_anthropic(system_text: str, user_text: str) -> Generator[str, None, None]:
    import anthropic
    from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── Groq (free tier) ──────────────────────────────────────────────────────────

def _generate_groq(system_text: str, user_text: str) -> str:
    from groq import Groq
    from .config import GROQ_API_KEY, GROQ_MODEL
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
    )
    return response.choices[0].message.content.strip()


def _stream_groq(system_text: str, user_text: str) -> Generator[str, None, None]:
    from groq import Groq
    from .config import GROQ_API_KEY, GROQ_MODEL
    client = Groq(api_key=GROQ_API_KEY)
    stream = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        stream=True,
    )
    for chunk in stream:
        text = chunk.choices[0].delta.content
        if text:
            yield text
