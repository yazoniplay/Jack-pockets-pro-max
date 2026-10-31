"""Validated timeline manifests passed from the editorial pipeline to Remotion."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class TimelineAsset(BaseModel):
    source_url: HttpUrl
    local_file: str = Field(min_length=1, max_length=300)
    title: str
    creator: str | None = None
    license_name: str
    license_url: HttpUrl | None = None
    attribution_required: bool = True


class TimelineScene(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["title", "footage", "chapter"]
    duration_frames: int = Field(ge=15, le=18000)
    title: str = Field(min_length=1, max_length=180)
    body: str = Field(default="", max_length=600)
    eyebrow: str = Field(default="", max_length=80)
    asset: TimelineAsset | None = None

    @model_validator(mode="after")
    def media_scenes_require_provenance(self):
        if self.kind == "footage" and self.asset is None:
            raise ValueError("Footage scenes require an asset with source and license metadata.")
        if self.kind != "footage" and self.asset is not None:
            raise ValueError("Only footage scenes may contain a media asset.")
        return self


class TimelineCaption(BaseModel):
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_frame <= self.start_frame:
            raise ValueError("Caption end_frame must be after start_frame.")
        return self


class TimelineManifest(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    scenes: list[TimelineScene] = Field(min_length=1, max_length=500)
    captions: list[TimelineCaption] = Field(default_factory=list)
    narration_file: str | None = None
    music_file: str | None = None
    fps: int = Field(default=30, ge=24, le=60)
    width: int = Field(default=1920, ge=640, le=3840)
    height: int = Field(default=1080, ge=360, le=2160)

    @model_validator(mode="after")
    def validate_timeline(self):
        seen_ids = set()
        previous_asset = None
        for scene in self.scenes:
            if scene.id in seen_ids:
                raise ValueError(f"Duplicate scene id: {scene.id}")
            seen_ids.add(scene.id)
            current_asset = str(scene.asset.source_url) if scene.asset else None
            if current_asset and current_asset == previous_asset:
                raise ValueError("Adjacent scenes cannot reuse the same footage source.")
            previous_asset = current_asset
        total_frames = sum(scene.duration_frames for scene in self.scenes)
        for caption in self.captions:
            if caption.end_frame > total_frames:
                raise ValueError("Caption extends beyond the end of the documentary timeline.")
        return self

    def to_remotion_props(self) -> dict:
        cursor = 0
        scenes = []
        for scene in self.scenes:
            scenes.append(
                {
                    "id": scene.id,
                    "kind": "footage" if scene.asset else scene.kind,
                    "durationInFrames": scene.duration_frames,
                    "title": scene.title,
                    "body": scene.body,
                    "eyebrow": scene.eyebrow,
                    "mediaSrc": scene.asset.local_file if scene.asset else None,
                    "mediaType": "video" if scene.asset else None,
                    "sourceCredit": (
                        f"Footage: {scene.asset.creator or 'Unknown creator'} · {scene.asset.license_name}"
                        if scene.asset else None
                    ),
                }
            )
            cursor += scene.duration_frames
        return {
            "title": self.title,
            "scenes": scenes,
            "captions": [
                {
                    "startFrame": caption.start_frame,
                    "endFrame": caption.end_frame,
                    "text": caption.text,
                }
                for caption in self.captions
            ],
            "narrationSrc": self.narration_file,
            "musicSrc": self.music_file,
        }
