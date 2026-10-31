# Jack Pockets Pro Max

An AI-assisted documentary video generator. Give it a topic; it builds a researched documentary plan, writes narration, prepares captions and visual instructions, then renders a finished video.

## Product workflow

1. **Brief** — topic, audience, target duration, language and editorial tone.
2. **Research** — gather source-backed claims and keep source URLs attached to each claim.
3. **Story** — create a structured documentary outline and narration draft.
4. **Editorial review** — check factual support, clarity, pacing and unsupported claims.
5. **Voice** — generate narration through a configured speech provider.
6. **Visual plan** — find licensed/reusable footage and stills; retain asset provenance and licensing metadata.
7. **Timeline** — assemble narration, captions, footage, maps and restrained graphics.
8. **Render + QA** — render the video and validate duration, audio, captions, media references and output integrity.

## Engineering principles

- **A video generator first.** Multi-model collaboration exists to improve documentary production, not as a separate chat product.
- **Provider adapters, not hard-coded vendors.** Claude, Gemini and OpenAI can participate as specialist reviewers when credentials are configured.
- **No fake collaboration.** Provider fallback is not collaboration. A collaborative run records each agent's input, critique and final synthesis.
- **Source provenance.** Research claims and media assets retain their source metadata.
- **Human approval gates.** Research and script can be reviewed before expensive media and rendering stages.
- **Fail honestly.** Missing credentials, unsupported media, weak sourcing and failed renders are explicit errors—not silently fabricated outputs.

## Current status

The repository is being initialized. The first milestone is a working API and pipeline foundation. The web interface, provider integrations, media acquisition and Remotion renderer will be added in tested stages.

## Planned stack

- Python 3.11+ / FastAPI — orchestration API and pipeline.
- TypeScript / React / Remotion — documentary timeline and rendering.
- FFmpeg / FFprobe — media processing and output validation.
- Optional LLM providers — Anthropic, Google Gemini and OpenAI.
- Optional speech and stock-media providers — configured independently.

## Configuration

Copy `.env.example` to `.env` and fill only the providers you have access to. Never commit API keys.

The ChatGPT app subscription does **not** automatically include OpenAI API credits. OpenAI API access requires its own API key and billing setup. The same principle applies to other hosted providers.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn jackpockets.api:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API.

## License

No license has been selected yet. Until one is added, all rights are reserved by default.
