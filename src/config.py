import os
from dotenv import load_dotenv

load_dotenv()

# ── Provider selection ────────────────────────────────────────────────────────
# Set LLM_PROVIDER=groq in .env to use Groq (free tier)
# Set LLM_PROVIDER=anthropic (default) to use Anthropic Claude
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# ── Groq (free tier) ──────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")

# ── Shared ────────────────────────────────────────────────────────────────────
LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

# ── Validation ────────────────────────────────────────────────────────────────
if LLM_PROVIDER == "groq":
    if not GROQ_API_KEY:
        raise EnvironmentError("GROQ_API_KEY ist nicht gesetzt. Kostenlos unter console.groq.com registrieren.")
elif LLM_PROVIDER == "anthropic":
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY ist nicht gesetzt. Oder LLM_PROVIDER=groq in .env setzen (kostenlos).")
else:
    raise EnvironmentError(f"Unbekannter LLM_PROVIDER: '{LLM_PROVIDER}'. Erlaubt: anthropic, groq")
