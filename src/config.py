import os
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=_env_path, override=True)

# ── LLM Provider ──────────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
# Validation always uses Claude for quality assurance regardless of LLM_PROVIDER
CLAUDE_VALIDATION_MODEL = os.getenv("CLAUDE_VALIDATION_MODEL", "claude-haiku-4-5-20251001")

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── Paths ─────────────────────────────────────────────────────────────────────
# On Vercel (and other serverless platforms) only /tmp is writable
_on_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
if _on_vercel:
    LOGS_DIR = "/tmp/logs"
else:
    LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")
PIPELINE_LOGS_DIR = os.path.join(LOGS_DIR, "pipeline")

# ── Google Sheets ─────────────────────────────────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
# Path to service account JSON file (alternative to inline JSON)
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
SHEETS_SPREADSHEET_ID = os.getenv("SHEETS_SPREADSHEET_ID", "")

# ── Google Drive ──────────────────────────────────────────────────────────────
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")

# ── Google Calendar ───────────────────────────────────────────────────────────
GCAL_CALENDAR_ID = os.getenv("GCAL_CALENDAR_ID", "primary")

# ── Cal.com ───────────────────────────────────────────────────────────────────
CALCOM_API_KEY = os.getenv("CALCOM_API_KEY", "")
CALCOM_EVENT_TYPE_ID = os.getenv("CALCOM_EVENT_TYPE_ID", "")
CALCOM_BASE_URL = os.getenv("CALCOM_BASE_URL", "https://api.cal.com/v2")

# ── Admin ─────────────────────────────────────────────────────────────────────
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

# ── Email (SMTP) ──────────────────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Immo AI")

# ── Automation ────────────────────────────────────────────────────────────────
AUTOMATION_POLL_INTERVAL = int(os.getenv("AUTOMATION_POLL_INTERVAL", "60"))
AUTOMATION_MAX_RETRIES = int(os.getenv("AUTOMATION_MAX_RETRIES", "3"))
AUTOMATION_WEBHOOK_SECRET = os.getenv("AUTOMATION_WEBHOOK_SECRET", "")

# ── Validation ────────────────────────────────────────────────────────────────
if LLM_PROVIDER == "groq":
    if not GROQ_API_KEY:
        raise EnvironmentError(
            "GROQ_API_KEY ist nicht gesetzt. Kostenlos unter console.groq.com registrieren."
        )
elif LLM_PROVIDER == "anthropic":
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY ist nicht gesetzt. Oder LLM_PROVIDER=groq in .env setzen (kostenlos)."
        )
else:
    raise EnvironmentError(
        f"Unbekannter LLM_PROVIDER: '{LLM_PROVIDER}'. Erlaubt: anthropic, groq"
    )
