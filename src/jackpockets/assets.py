"""Licensed stock-footage discovery and safe Pexels asset downloads."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import get_settings
from .providers import ProviderError


class AssetError(RuntimeError):
    """Stock footage discovery or download failed."""


@dataclass(frozen=True)
class FootageCandidate:
    provider: str
    provider_id: str
    title: str
    creator: str
    page_url: str
    download_url: str
    width: int
    height: int
    duration_seconds: int
    license_name: str
    license_url: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    thumbnail_url: str | None = None


def choose_video_file(files: list[dict]) -> dict | None:
    """Choose the largest usable MP4 rendition, preferring 1080p or higher."""
    usable = [
        item for item in files
        if item.get("file_type") == "video/mp4" and item.get("link")
    ]
    if not usable:
        return None
    return max(
        usable,
        key=lambda item: (
            int(item.get("width") or 0) >= 1920,
            int(item.get("width") or 0) * int(item.get("height") or 0),
            int(item.get("width") or 0),
        ),
    )


def rank_footage_candidates(
    candidates: list[FootageCandidate],
    target_duration_seconds: float | None = None,
) -> list[dict]:
    """Rank search results by technical fit, using provider order only as a weak tie-breaker."""
    ranked = []
    for search_position, candidate in enumerate(candidates):
        provider_order_score = max(0, 20 - search_position * 2)
        if candidate.width >= 1920 and candidate.height >= 1080:
            resolution_score = 35
            resolution_label = "1080p+"
        elif candidate.width >= 1280 and candidate.height >= 720:
            resolution_score = 26
            resolution_label = "720p"
        else:
            resolution_score = 12
            resolution_label = "below 720p"
        ratio = candidate.width / candidate.height if candidate.height else 0
        ratio_score = max(0, round(20 - abs(ratio - (16 / 9)) * 18))
        ratio_label = "16:9" if abs(ratio - (16 / 9)) <= 0.08 else f"{ratio:.2f}:1"
        if target_duration_seconds and target_duration_seconds > 0:
            duration_score = round(25 * min(candidate.duration_seconds / target_duration_seconds, 1))
            duration_label = (
                "covers beat" if candidate.duration_seconds >= target_duration_seconds
                else "shorter than beat"
            )
        else:
            duration_score = 25 if 6 <= candidate.duration_seconds <= 45 else 16
            duration_label = f"{candidate.duration_seconds}s"
        score = provider_order_score + resolution_score + ratio_score + duration_score
        ranked.append({
            **candidate.__dict__,
            "quality_score": min(100, score),
            "quality_notes": [
                f"Resolution: {resolution_label}",
                f"Frame: {ratio_label}",
                f"Duration: {duration_label}",
            ],
            "search_position": search_position + 1,
        })
    return sorted(ranked, key=lambda item: item["quality_score"], reverse=True)


_TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
_STOPWORDS = {"about", "after", "again", "also", "among", "because", "before", "being", "between", "could", "during", "from", "have", "into", "more", "most", "other", "over", "same", "some", "than", "that", "their", "there", "these", "they", "this", "those", "through", "under", "very", "what", "when", "where", "which", "while", "with", "would", "your", "viewer", "footage", "shot", "visual", "scene", "documentary"}

def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(value) if token.lower() not in _STOPWORDS}

def semantic_relevance(candidate: FootageCandidate, narration_excerpt: str, visual_description: str, visual_query: str) -> dict:
    """Score metadata evidence against the spoken meaning and intended visual."""
    intent = _tokens(f"{narration_excerpt} {visual_description} {visual_query}")
    tag_tokens = _tokens(" ".join(candidate.tags))
    title_tokens = _tokens(candidate.title)
    slug = candidate.page_url.rstrip("/").rsplit("/", 1)[-1]
    url_tokens = _tokens(slug)
    metadata = tag_tokens | title_tokens | url_tokens
    if not intent or not metadata:
        return {"score": 0, "notes": ["Provider supplied insufficient descriptive metadata; visual relevance is unverified"], "evidence": "insufficient"}
    tag_hits = intent & tag_tokens
    title_hits = intent & (title_tokens | url_tokens)
    weighted_hits = len(tag_hits) * 2.0 + len(title_hits)
    score = round(min(100, weighted_hits / max(1.0, len(intent) * 2.0) * 100))
    notes = []
    if tag_hits: notes.append("Tags match: " + ", ".join(sorted(tag_hits)[:5]))
    if title_hits: notes.append("Title/context match: " + ", ".join(sorted(title_hits)[:5]))
    if not notes: notes.append("No matching topic terms found in provider metadata")
    evidence = "metadata" if tag_tokens else "limited_metadata" if title_hits else "insufficient"
    return {"score": score, "notes": notes, "evidence": evidence}

def rank_editorial_candidates(candidates: list[FootageCandidate], narration_excerpt: str, visual_description: str, visual_query: str, target_duration_seconds: float | None = None) -> list[dict]:
    """Combine explainable metadata relevance with independent technical fit."""
    technical = rank_footage_candidates(candidates, target_duration_seconds)
    by_id = {item.provider_id: item for item in candidates}
    ranked = []
    for item in technical:
        relevance = semantic_relevance(by_id[item["provider_id"]], narration_excerpt, visual_description, visual_query)
        item["semantic_score"] = relevance["score"]
        item["semantic_notes"] = relevance["notes"]
        item["semantic_evidence"] = relevance["evidence"]
        item["editorial_score"] = (
            round(relevance["score"] * 0.7 + item["quality_score"] * 0.3)
            if relevance["evidence"] != "insufficient"
            else item["quality_score"]
        )
        item["editorial_basis"] = "metadata_plus_technical" if relevance["evidence"] != "insufficient" else "technical_fallback"
        ranked.append(item)
    return sorted(ranked, key=lambda item: item["editorial_score"], reverse=True)

async def evaluate_visual_candidates(
    ranked_candidates: list[dict],
    narration_excerpt: str,
    visual_description: str,
    visual_query: str,
    provider,
) -> list[dict]:
    """Use a configured multimodal model to inspect Pexels preview frames."""
    if not provider or not hasattr(provider, "generate_with_images"):
        return ranked_candidates
    candidates = ranked_candidates[:5]
    images: list[tuple[bytes, str]] = []
    image_ids: list[str] = []
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        for candidate in candidates:
            thumbnail = candidate.get("thumbnail_url")
            if not thumbnail:
                continue
            parsed = urlparse(thumbnail)
            host = parsed.hostname or ""
            if parsed.scheme != "https" or not (host == "pexels.com" or host.endswith(".pexels.com")):
                continue
            try:
                response = await client.get(thumbnail)
                response.raise_for_status()
                final_host = urlparse(str(response.url)).hostname or ""
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                if not (final_host == "pexels.com" or final_host.endswith(".pexels.com")):
                    continue
                if content_type not in {"image/jpeg", "image/png", "image/webp"} or len(response.content) > 2_000_000:
                    continue
                images.append((response.content, content_type))
                image_ids.append(str(candidate["provider_id"]))
            except (httpx.HTTPError, KeyError, TypeError):
                continue
    if not images:
        for item in ranked_candidates:
            item["visual_evidence"] = "preview_unavailable"
            item["visual_notes"] = ["No safe preview frame was available for visual inspection"]
        return ranked_candidates
    image_guide = "\n".join(f"Image {index + 1} corresponds to Pexels clip ID {provider_id}." for index, provider_id in enumerate(image_ids))
    prompt = (
        "Inspect each supplied video preview frame as documentary footage. "
        "Judge only what is visibly present; do not infer hidden context, identity, date, or location. "
        "Compare each image with the narration excerpt, intended visual description, and search intent. "
        "Score semantic visual relevance from 0 to 100. Penalize generic or misleading imagery. "
        "Return JSON only: {\"scores\":[{\"provider_id\":\"...\",\"score\":0,\"reason\":\"short evidence-based explanation\"}]}.\n\n"
        f"NARRATION: {narration_excerpt}\nVISUAL INTENT: {visual_description}\nSEARCH INTENT: {visual_query}\n\n{image_guide}"
    )
    try:
        reply = await provider.generate_with_images(
            "You are a rigorous documentary visual editor. Evaluate only visible evidence and be conservative.",
            prompt,
            images,
        )
        raw = reply.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].removesuffix("```").strip()
        payload = json.loads(raw)
        scores = {str(item["provider_id"]): item for item in payload.get("scores", [])}
    except (ProviderError, httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        for item in ranked_candidates:
            item["visual_evidence"] = "evaluation_failed"
            item["visual_notes"] = ["Visual model evaluation failed; metadata and technical ranking retained"]
        return ranked_candidates
    for item in ranked_candidates:
        score = scores.get(str(item["provider_id"]))
        if score is None:
            item["visual_evidence"] = "not_scored"
            item["visual_notes"] = ["No visual assessment returned for this clip"]
            continue
        visual_score = max(0, min(100, int(score.get("score", 0))))
        item["visual_score"] = visual_score
        item["visual_notes"] = [str(score.get("reason", "Visual match assessed"))[:240]]
        item["visual_evidence"] = "gemini_preview_frame"
        item["editorial_basis"] = "visual_plus_metadata_and_technical"
        item["editorial_score"] = round(
            visual_score * 0.65 + item.get("semantic_score", 0) * 0.2 + item.get("quality_score", 0) * 0.15
        )
    return sorted(ranked_candidates, key=lambda item: item.get("editorial_score", 0), reverse=True)
def diversify_storyboard_recommendations(recommendations: list[dict]) -> list[dict]:
    """Choose distinct primary clips across beats without hiding alternatives."""
    used: set[str] = set()
    ordered = sorted(recommendations, key=lambda item: max((candidate.get("editorial_score", 0) for candidate in item.get("results", [])), default=0), reverse=True)
    for item in ordered:
        available = [candidate for candidate in item.get("results", []) if candidate.get("provider_id") not in used]
        if available:
            primary = available[0]
            used.add(primary["provider_id"])
            item["recommended_provider_id"] = primary["provider_id"]
            item["diversity_note"] = "Unique clip selected for this beat"
            for candidate in item.get("results", []):
                candidate["recommended_for_beat"] = candidate["provider_id"] == primary["provider_id"]
        else:
            item["recommended_provider_id"] = None
            item["diversity_note"] = "All returned clips overlap with stronger beat matches"
    return recommendations

class PexelsClient:
    LICENSE_URL = "https://www.pexels.com/license/"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_settings().pexels_api_key
        if not self.api_key:
            raise AssetError("PEXELS_API_KEY is required for stock-footage search.")

    async def search_videos(self, query: str, per_page: int = 12) -> list[FootageCandidate]:
        if not query.strip() or len(query) > 160:
            raise AssetError("Footage search query must contain 1–160 characters.")
        per_page = max(1, min(per_page, 30))
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": self.api_key},
                params={"query": query, "per_page": per_page, "orientation": "landscape"},
            )
        if response.status_code == 401:
            raise AssetError("Pexels rejected the API key. Check PEXELS_API_KEY.")
        if response.status_code == 429:
            raise AssetError("Pexels rate limit reached. Retry later.")
        response.raise_for_status()
        candidates = []
        for video in response.json().get("videos", []):
            rendition = choose_video_file(video.get("video_files", []))
            if not rendition:
                continue
            candidates.append(
                FootageCandidate(
                    provider="pexels",
                    provider_id=str(video["id"]),
                    title=f"Pexels footage {video['id']}",
                    creator=video.get("user", {}).get("name", "Unknown creator"),
                    page_url=video.get("url", ""),
                    download_url=rendition["link"],
                    width=int(rendition.get("width") or 0),
                    height=int(rendition.get("height") or 0),
                    duration_seconds=int(video.get("duration") or 0),
                    license_name="Pexels License",
                    license_url=self.LICENSE_URL,
                    tags=tuple(str(tag.get("name", "")) if isinstance(tag, dict) else str(tag) for tag in video.get("tags", []) if tag)[:20],
                    thumbnail_url=(video.get("video_pictures", [{}])[len(video.get("video_pictures", [])) // 2].get("picture") if video.get("video_pictures") else video.get("image")),
                )
            )
        return candidates


async def download_pexels_video(
    candidate: FootageCandidate,
    destination: str | Path,
    max_bytes: int = 500_000_000,
) -> Path:
    """Download only Pexels-hosted MP4 media and enforce a hard size ceiling."""
    parsed = urlparse(candidate.download_url)
    if parsed.scheme != "https" or not (
        parsed.hostname == "pexels.com" or (parsed.hostname or "").endswith(".pexels.com")
    ):
        raise AssetError("Refusing media download from a non-Pexels host.")
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client, client.stream(
            "GET", candidate.download_url
        ) as response:
                response.raise_for_status()
                final_host = urlparse(str(response.url)).hostname or ""
                if not (final_host == "pexels.com" or final_host.endswith(".pexels.com")):
                    raise AssetError("Pexels download redirected to an untrusted host.")
                content_length = int(response.headers.get("content-length") or 0)
                if content_length > max_bytes:
                    raise AssetError("Footage file exceeds the configured download limit.")
                with target.open("wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise AssetError("Footage file exceeded the download limit.")
                        output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise AssetError("Pexels returned an empty media file.")
    return target
