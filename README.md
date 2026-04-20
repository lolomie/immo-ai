# Immo AI — MVP

AI-assisted exposé generation for German real estate agencies.

**Pipeline:** Input JSON → Generate (Claude) → Validate (hallucination check) → Human review → Approved text

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

## Run

```bash
# Generate and validate an exposé
python workflows/run.py --input docs/example_property.json

# Review pending jobs (approve / reject)
python workflows/review.py
```

## Output

- `logs/{job_id}.json` — full job record (status, exposé text, validation result)
- `logs/{job_id}_approved.txt` — clean exposé text after human approval

---

## Hard Rules

- No auto-publishing. Human must approve every exposé.
- All exposés end with: `⚠️ KI-generiert — vor Veröffentlichung prüfen.`
- `notes` field (agent notes) is never sent to the LLM or stored in logs.

## Input Format

See `docs/example_property.json` for the full schema. Required fields:
`property_id`, `address`, `city`, `zip_code`, `property_type`, `size_sqm`, `rooms`

All other fields are optional — the LLM will omit missing sections.

## Model

Default: `claude-haiku-4-5`. Override in `.env`:
```
CLAUDE_MODEL=claude-sonnet-4-6
```
