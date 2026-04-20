# PLAN.md

## Current Phase: v0.1 — Core MVP

## Status
- [x] Project scaffold
- [x] Data models (PropertyInput, JobResult)
- [x] Prompt templates (generation, validation)
- [x] Exposé generator (src/generator.py)
- [x] Hallucination validator (src/validator.py)
- [x] Main CLI workflow (workflows/run.py)
- [x] Human review CLI (workflows/review.py)
- [x] Test fixture (docs/example_property.json)
- [ ] End-to-end test with real API key
- [ ] Git init + commits

## Next Steps
- Test with real ANTHROPIC_API_KEY
- Run 3 different property types through pipeline
- Tune prompts if output quality is poor

## Stretch Goals (v0.2)
- Calendar stub (src/calendar_service.py)
- Batch mode: --batch docs/properties/
- FastAPI wrapper (api/main.py)
