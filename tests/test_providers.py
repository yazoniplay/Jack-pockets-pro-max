import asyncio
import base64

from jackpockets.providers import GeminiProvider, GroqProvider, OllamaProvider


def test_gemini_multimodal_request_encodes_preview_frames(monkeypatch) -> None:
    provider = GeminiProvider("test-key", "gemini-test")
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"candidates": [{"content": {"parts": [{"text": '{"scores":[]}'}]}}]}

    monkeypatch.setattr(provider, "_post", fake_post)
    reply = asyncio.run(provider.generate_with_images("visual editor", "score these frames", [(b"frame-bytes", "image/jpeg")]))

    assert reply.text == '{"scores":[]}'
    parts = captured["payload"]["contents"][0]["parts"]
    assert parts[1]["inline_data"]["mime_type"] == "image/jpeg"
    assert base64.b64decode(parts[1]["inline_data"]["data"]) == b"frame-bytes"
    assert captured["payload"]["generationConfig"]["responseMimeType"] == "application/json"


def test_ollama_uses_configured_openai_compatible_endpoint(monkeypatch) -> None:
    provider = OllamaProvider(None, "gpt-oss:20b", "http://127.0.0.1:11434/v1")
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Fact check complete."}}]}

    monkeypatch.setattr(provider, "_post", fake_post)
    reply = asyncio.run(provider.generate("system", "check this claim"))
    assert reply.provider == "ollama"
    assert reply.model == "gpt-oss:20b"
    assert reply.text == "Fact check complete."
    assert captured["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert "Authorization" not in captured["headers"]


def test_groq_uses_bearer_auth_and_openai_compatible_endpoint(monkeypatch) -> None:
    provider = GroqProvider("groq-test-key", "openai/gpt-oss-120b", "https://api.groq.com/openai/v1")
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Story structure complete."}}]}

    monkeypatch.setattr(provider, "_post", fake_post)
    reply = asyncio.run(provider.generate("system", "build the story"))
    assert reply.provider == "groq"
    assert reply.text == "Story structure complete."
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer groq-test-key"
