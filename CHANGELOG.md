# CHANGELOG.md

## [0.1.0] — 2026-04-20

### Added
- Full project scaffold (src/, workflows/, prompts/, logs/, docs/)
- `src/models.py` — PropertyInput and JobResult Pydantic models
- `src/config.py` — Environment-based configuration
- `src/generator.py` — Claude API call for exposé generation
- `src/validator.py` — Claude API call for hallucination detection (yes/no)
- `prompts/generation.txt` — German real estate generation prompt
- `prompts/validation.txt` — Hallucination validation prompt
- `workflows/run.py` — Main CLI: generate → validate → save to logs
- `workflows/review.py` — Human review CLI: approve / reject pending jobs
- `docs/example_property.json` — Test fixture
- `README.md`, `PLAN.md`, `MEMORY.md`, `CHANGELOG.md`
- `.env.example`, `requirements.txt`, `.gitignore`
