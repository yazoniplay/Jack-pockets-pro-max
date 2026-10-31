# Jack Pockets Pro Max

An AI documentary video generator. Enter a topic and build a documentary through research, story development, narration, visual planning, editing and quality assurance.

The current working milestone is a persistent job API and multi-provider planning roundtable. It is not yet a complete MP4 generator.

## Current capabilities
- Persistent SQLite documentary jobs and event history.
- FastAPI endpoints to create, list and inspect jobs.
- Native REST adapters for Anthropic Claude, Google Gemini and OpenAI.
- Parallel specialist agents: research editor, story architect and skeptical fact-checker.
- Cross-review round, followed by an executive synthesis.
- Explicit single-provider vs multi-agent run labeling.
- Provider timeouts, bounded retries and actionable errors.
- Human review state before later production stages.
- GitHub Actions lint and test workflow.

## Product pipeline
1. Brief — topic, duration, language, audience and editorial tone.
2. Research — source discovery, primary-source preference, claim extraction and provenance.
3. Story — outline, act structure, narration and transitions.
4. Editorial review — cross-model critique, factual review and human approval.
5. Voice — narration generation and timing.
6. Visual research — footage and still discovery with licensing/provenance metadata.
7. Timeline — narration, captions, media, maps, charts and restrained graphics.
8. Render — Remotion composition and FFmpeg processing.
9. Quality assurance — source coverage, pacing, captions, audio, media reuse and final MP4 validation.

## Multi-model collaboration
The roundtable is not a provider fallback chain. When all three keys are configured, the application assigns distinct specialist roles to Gemini, Claude and OpenAI, runs them concurrently, lets the configured agents critique the combined work, then asks an executive synthesis model to reconcile disagreements.

A run with fewer than two successful providers is explicitly labeled as single-provider work. The system never describes that as full collaboration.

Provider roles: Gemini is the research editor, Claude is the story architect, and OpenAI is the skeptical fact-checker and preferred synthesis provider. These are orchestration roles, not claims that a model has independently verified facts. Research claims still need traceable sources and human review.

## Setup
Requirements: Python 3.11+.

1. Create and activate a Python virtual environment.
2. Install dependencies with: pip install -e ".[dev]"
3. Copy .env.example to .env.
4. Add the provider API keys you actually have.
5. Start the API with: uvicorn jackpockets.api:app --reload

API docs: http://127.0.0.1:8000/docs

## API
Create a job with POST /api/jobs and JSON body:

    {"brief":{"topic":"How the Panama Canal changed global trade","target_minutes":12}}

Start its planning roundtable with POST /api/jobs/{job_id}/run. Inspect status and agent output with GET /api/jobs/{job_id}. Provider readiness is available at GET /api/providers.

## Credentials and cost
Add provider API keys to .env. Never commit .env or paste secret keys into issues. Consumer ChatGPT, Claude and Gemini subscriptions do not automatically provide API credits. Hosted API calls may incur separate charges. The app does not make provider calls until a job is explicitly run.

## Development
Run ruff check . and pytest.

## Honest status
The current code implements the job API and AI planning roundtable. It does not yet perform grounded web research, generate narration audio, acquire footage, compose a Remotion timeline or render an MP4. Those are the next engineering milestones; the README will be updated as each becomes functional and tested.

## Security
Secrets are environment-only. Provider error output is bounded. CORS defaults to local development origins. SQLite uses parameterized queries and foreign keys. Production deployment still needs authentication, authorization, rate limiting, encrypted secret management and durable worker infrastructure.

## License
No license has been selected. All rights are reserved by default.