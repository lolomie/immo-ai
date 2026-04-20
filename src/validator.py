import json
import os
import re
import anthropic

from .config import CLAUDE_MODEL, PROMPTS_DIR
from .models import PropertyInput


def validate_expose(property_data: PropertyInput, expose_text: str) -> dict:
    """Returns {"hallucinated": bool, "details": str}"""
    template_path = os.path.join(PROMPTS_DIR, "validation.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        prompt = f.read()

    data_for_llm = property_data.model_dump(exclude={"notes"})
    property_json = json.dumps(data_for_llm, ensure_ascii=False, indent=2)

    prompt = prompt.replace("{property_json}", property_json)
    prompt = prompt.replace("{expose_text}", expose_text)

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if match:
        raw = match.group(1)

    try:
        result = json.loads(raw)
        return {
            "hallucinated": bool(result.get("hallucinated", False)),
            "details": str(result.get("details", "")),
        }
    except json.JSONDecodeError:
        # If model didn't return valid JSON, treat as inconclusive — flag for human
        return {
            "hallucinated": True,
            "details": f"Validierung fehlgeschlagen (kein gültiges JSON): {raw[:200]}",
        }
