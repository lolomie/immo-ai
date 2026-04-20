# MEMORY.md

## Architecture Decisions

- **No scoring system** — Validation is binary: hallucinated yes/no. Avoids false precision.
- **File-based logs** — One JSON per job in `/logs`. No database. Simple and auditable.
- **notes field excluded** — Agent notes never sent to LLM or saved in logs (GDPR).
- **No auto-approve** — Hard rule. Human must approve every job via review.py.
- **Prompts as .txt files** — Non-technical users can edit prompts without touching Python.
- **Two Claude calls per job** — One for generation, one for validation. Expected cost: ~$0.001/job on Haiku.

## Known Issues / Watch Points
- If model returns non-JSON from validation prompt, validator flags as hallucinated (safe default).
- `logs/` is gitignored — do not commit job files.

## Assumptions
- Input JSON is always UTF-8.
- Property data is trusted (pre-validated by the agent submitting it).
- MVP is single-user CLI, no concurrency concerns.
