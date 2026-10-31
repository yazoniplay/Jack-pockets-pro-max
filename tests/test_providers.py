import asyncio
import base64

from jackpockets.providers import GeminiProvider


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