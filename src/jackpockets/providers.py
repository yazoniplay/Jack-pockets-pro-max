"""Small, explicit REST adapters for supported LLM providers.

No provider SDK is required. Provider credentials are read only from environment
variables and are never included in API responses or logs.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from .config import get_settings


class ProviderError(RuntimeError):
    """A provider request failed in a user-actionable way."""


@dataclass(frozen=True)
class ModelReply:
    provider: str
    model: str
    text: str
    sources: list[dict[str, str]] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(self, system: str, prompt: str) -> ModelReply: ...


class RESTProvider:
    name = "unknown"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        settings = get_settings()
        self.timeout = settings.request_timeout_seconds
        self.retries = settings.max_provider_retries

    async def _post(self, url: str, headers: dict[str, str], payload: dict) -> dict:
        last_error = "unknown provider error"
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"temporary HTTP {response.status_code}"
                    if attempt < self.retries:
                        await asyncio.sleep(min(2 ** attempt, 8))
                        continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = type(exc).__name__
                if attempt < self.retries:
                    await asyncio.sleep(min(2 ** attempt, 8))
                    continue
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:500]
                raise ProviderError(
                    f"{self.name} returned HTTP {exc.response.status_code}: {detail}"
                ) from exc
            except ValueError as exc:
                raise ProviderError(f"{self.name} returned invalid JSON.") from exc
        raise ProviderError(f"{self.name} request failed after retries: {last_error}")

    async def generate(self, system: str, prompt: str) -> ModelReply:
        raise NotImplementedError


class OpenAIProvider(RESTProvider):
    name = "openai"

    async def generate(self, system: str, prompt: str) -> ModelReply:
        data = await self._post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            {
                "model": self.model,
                "temperature": 0.4,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI response did not contain message text.") from exc
        return ModelReply(self.name, self.model, text)


class AnthropicProvider(RESTProvider):
    name = "anthropic"

    async def generate(self, system: str, prompt: str) -> ModelReply:
        data = await self._post(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            {
                "model": self.model,
                "max_tokens": 5000,
                "temperature": 0.4,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        try:
            text = "\n".join(
                item["text"] for item in data["content"] if item.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise ProviderError("Anthropic response did not contain message text.") from exc
        return ModelReply(self.name, self.model, text)


class OpenAICompatibleProvider(RESTProvider):
    """Provider adapter for Ollama and Groq OpenAI-compatible chat APIs."""

    base_url = ""

    def __init__(self, api_key: str | None, model: str, base_url: str):
        super().__init__(api_key or "", model)
        self.base_url = base_url.rstrip("/")

    async def generate(self, system: str, prompt: str) -> ModelReply:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = await self._post(
            f"{self.base_url}/chat/completions",
            headers,
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        try:
            text = data["choices"][0]["message"]["content"]
            if isinstance(text, list):
                text = "\\n".join(
                    item.get("text", "") for item in text if isinstance(item, dict)
                )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name} response did not contain message text.") from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(f"{self.name} returned an empty response.")
        return ModelReply(self.name, self.model, text)


class OllamaProvider(OpenAICompatibleProvider):
    name = "ollama"


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"


class GeminiProvider(RESTProvider):
    name = "gemini"

    async def generate(self, system: str, prompt: str) -> ModelReply:
        return await self._generate(system, prompt, grounded=False)

    async def generate_with_images(self, system: str, prompt: str, images: list[tuple[bytes, str]]) -> ModelReply:
        """Evaluate supplied visual evidence using Gemini's multimodal input."""
        parts = [{"text": prompt}]
        for image_bytes, mime_type in images:
            parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}})
        data = await self._post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}",
            {"Content-Type": "application/json"},
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"maxOutputTokens": 2500, "responseMimeType": "application/json"},
            },
        )
        try:
            text = "\n".join(part["text"] for part in data["candidates"][0]["content"]["parts"] if "text" in part)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini visual response did not contain structured text.") from exc
        return ModelReply(self.name, self.model, text)
    async def generate_grounded(self, system: str, prompt: str) -> ModelReply:
        """Use Gemini Google Search grounding for research-stage discovery."""
        return await self._generate(system, prompt, grounded=True)

    async def _generate(self, system: str, prompt: str, grounded: bool) -> ModelReply:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 5000},
        }
        if grounded:
            payload["tools"] = [{"google_search": {}}]
        data = await self._post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}",
            {"Content-Type": "application/json"},
            payload,
        )
        try:
            text = "\n".join(
                part["text"]
                for part in data["candidates"][0]["content"]["parts"]
                if "text" in part
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini response did not contain candidate text.") from exc
        sources = []
        if grounded:
            chunks = data.get("candidates", [{}])[0].get("groundingMetadata", {}).get("groundingChunks", [])
            for chunk in chunks:
                web = chunk.get("web", {})
                uri = web.get("uri")
                if uri:
                    sources.append({"title": web.get("title", uri), "url": uri})
        return ModelReply(self.name, self.model, text, sources)


def configured_providers() -> dict[str, LLMProvider]:
    settings = get_settings()
    providers: dict[str, LLMProvider] = {}
    if settings.gemini_api_key:
        providers["gemini"] = GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if settings.ollama_api_key or settings.ollama_base_url.startswith(
        ("http://localhost", "http://127.0.0.1")
    ):
        providers["ollama"] = OllamaProvider(
            settings.ollama_api_key, settings.ollama_model, settings.ollama_base_url
        )
    if settings.groq_api_key:
        providers["groq"] = GroqProvider(
            settings.groq_api_key, settings.groq_model, settings.groq_base_url
        )
    return providers
