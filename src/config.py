import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

if not ANTHROPIC_API_KEY:
    raise EnvironmentError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
