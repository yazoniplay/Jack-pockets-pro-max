# Jack Pockets Pro Max

**An AI documentary video generator.** The product turns a topic into a source-aware documentary plan, reviewed narration, selected footage, a timed timeline and a validated MP4.

## Implemented now
- Persistent SQLite jobs with an append-only event history.
- FastAPI API for job creation, status, review stages and outputs.
- Native REST adapters for Google Gemini, Ollama GPT-OSS and Groq.
- Parallel specialist agents, cross-model critique and executive synthesis.
- Duration-aware full narration drafting from the editorial synthesis.
- Independent second-model narration audit with explicit factual-risk feedback.
- Gemini Google Search grounding for research-stage source discovery; returned grounding URLs are preserved with the agent contribution.
- Explicit single-provider vs multi-agent labeling. A fallback or solo run is never called collaboration.
- Pexels stock-footage search and constrained download with creator, source page, license metadata and preview frames.
- Beat-level editorial ranking that separates visual relevance from technical fit, with evidence notes and a cross-beat diversity pass to avoid reusing the same clip.
- Optional Gemini multimodal review of Pexels preview frames against the exact narration excerpt and visual intent. The bulk workflow caps this at 12 beat reviews per run; other beats retain transparent metadata/technical ranking.
- Optional Edge TTS narration with word-boundary captions mapped to timeline frames.
- Pydantic timeline validation: asset provenance, unique scene IDs, caption bounds and adjacent-footage reuse checks.
- Remotion 1920x1080 / 30fps composition with cinematic crossfades, slow camera movement, animated captions, narration and music.
- Original procedural ambient soundtrack generation with stereo modulation, fade envelopes, loudness limiting and caption-aware narration ducking; no stock track is downloaded.
- FFprobe-based MP4 validation and a guarded video retrieval endpoint.
- GitHub Actions CI for Python tests/lint and renderer TypeScript checks.

## Documentary workflow
1. Create a job with topic, target length, language, audience and tone.
2. Run the AI roundtable. Gemini researches with Google Search grounding, Groq develops story structure and synthesizes the package, and Ollama GPT-OSS performs skeptical fact review when all three providers are configured.
3. Inspect the agent drafts, critiques, source manifest and synthesis. The system drafts a full narration script and, when another provider is available, runs an independent factual-risk audit. Resolve disputed claims and edit the script; human approval remains mandatory.
4. Submit the approved narration text. Edge TTS generates MP3 audio and word-boundary captions.
5. Search Pexels for footage. The editor compares preview frames with each beat's narration and visual intent when a Gemini API key is configured, ranks visual relevance separately from technical fit, and recommends unique clips across adjacent beats. Review and select clips; downloads retain source and license metadata. The renderer can compose an original ambient score locally, or run without music.
6. Submit a validated timeline manifest containing scenes, downloaded assets, narration and captions.
7. Remotion renders the MP4. FFprobe checks video/audio streams, duration and resolution before the job is marked complete.

## Setup
Requirements: Python 3.11+, Node.js 20+, npm, FFmpeg and FFprobe.

Python setup:
    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev,media]"
    cp .env.example .env
    uvicorn jackpockets.api:app --reload

Renderer setup in a second terminal:
    cd renderer
    npm install
    npm run typecheck

Dashboard setup in a third terminal:
    cd web
    npm install
    cp .env.example .env
    npm run dev

Open http://127.0.0.1:5173. The dashboard connects to the API at VITE_API_BASE_URL.

API docs: http://127.0.0.1:8000/docs

## Provider configuration and costs
Add API keys to .env. Gemini and Groq API usage may be billed separately from consumer chat subscriptions. Ollama local inference runs on your own hardware; Ollama Cloud requires its own API key and may have usage limits or charges. Pexels API access is optional. Edge TTS is an online speech service and requires network access. Rendering is local and requires the Remotion dependencies plus FFmpeg/FFprobe.

## API overview
- POST /api/jobs — create a documentary job.
- POST /api/jobs/{id}/run — run the AI planning roundtable.
- GET /api/jobs/{id} — inspect state, agent contributions, critiques, sources and events.
- GET /api/providers — inspect configured model providers.
- GET /api/assets/search?query=... — discover Pexels footage.
- POST /api/jobs/{id}/assets — download a selected Pexels clip into the job's local asset folder.
- POST /api/jobs/{id}/narration — synthesize approved script text and timed word captions.
- POST /api/jobs/{id}/render — validate and render a supplied timeline manifest.
- GET /api/jobs/{id}/video — retrieve the validated MP4.

## Current limitations
The production stages exist as real modules and API endpoints, but the whole experience is not yet a one-click autonomous pipeline. Editorial approval and timeline assembly are explicit steps; fully autonomous final shot approval, deeper multi-frame video understanding, music-provider integrations and production-grade distributed queue are still future work. Production deployment also needs authentication, rate limiting, durable worker infrastructure and managed secret storage.

## Security and editorial standards
Secrets are environment-only. Footage downloads are restricted to Pexels-hosted URLs and bounded by a size ceiling. Renderer asset paths are confined to renderer/public. Jobs are persisted with parameterized SQLite operations. AI output is treated as a draft: source grounding is not proof, and factual claims require editorial review.

## License
No license has been selected. All rights are reserved by default.

Recent production-quality safeguards include beat-aware technical footage ranking, narration-to-storyboard duration checks and final MP4 runtime verification.

- One-click bulk Pexels discovery across every storyboard beat, with Gemini preview-frame review (up to 12 beats per run), metadata relevance, technical fit, cross-beat clip diversity and explicit human selection.
