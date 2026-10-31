"""Licensed stock-footage discovery and safe Pexels asset downloads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import get_settings


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
    """Rank relevant search results by technical suitability without inventing relevance."""
    ranked = []
    for search_position, candidate in enumerate(candidates):
        relevance_score = max(0, 20 - search_position * 2)
        pixels = candidate.width * candidate.height
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
        score = relevance_score + resolution_score + ratio_score + duration_score
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
