import json
import os
import anthropic

from .config import CLAUDE_MODEL, PROMPTS_DIR
from .models import PropertyInput


def generate_expose(property_data: PropertyInput) -> str:
    template_path = os.path.join(PROMPTS_DIR, "generation.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        prompt = f.read()

    # Strip notes/PII before sending to LLM
    data_for_llm = property_data.model_dump(exclude={"notes"})
    property_json = json.dumps(data_for_llm, ensure_ascii=False, indent=2)

    prompt = prompt.replace("{property_json}", property_json)

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text.strip()
