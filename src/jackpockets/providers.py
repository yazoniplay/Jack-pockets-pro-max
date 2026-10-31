"""Small, explicit REST adapters for supported LLM providers.

No provider SDK is required. Provider credentials are read only from environment
variables and are never included in API responses or logs.
"""

from __future__ import annotations

import asyncio
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


class GeminiProvider(RESTProvider):
    name = "gemini"

    async def generate(self, system: str, prompt: str) -> ModelReply:
        return await self._generate(system, prompt, grounded=False)

    async def generate_grounded(self, system: str, prompt: str) -> ModelReply:
        """Use Gemini Google Search grounding for research-stage discovery."""
        return await self._generate(system, prompt, grounded=True)

    async def _generate(self, system: str, prompt: str, grounded: bool) -> ModelReply:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 5000},
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
    if settings.anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(
            settings.anthropic_api_key, settings.anthropic_model
        )
    if settings.gemini_api_key:
        providers["gemini"] = GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if settings.openai_api_key:
        providers["openai"] = OpenAIProvider(settings.openai_api_key, settings.openai_model)
    return providers
