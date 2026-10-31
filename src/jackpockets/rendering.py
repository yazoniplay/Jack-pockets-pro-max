"""Run Remotion with a validated local manifest and inspect the final MP4."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .media import MediaError, MediaReport, probe_media, validate_render
from .timeline import TimelineManifest


def _public_asset(renderer_dir: Path, relative_path: str) -> Path:
    public_dir = (renderer_dir / "public").resolve()
    target = (public_dir / relative_path).resolve()
    if not target.is_relative_to(public_dir):
        raise MediaError("Asset path escapes the renderer public directory.")
    if not target.is_file():
        raise MediaError(f"Required local asset is missing: {relative_path}")
    return target


def _validate_narration_alignment(
    narration_duration_seconds: float,
    timeline_frames: int,
    fps: int,
    tolerance_seconds: float = 1.5,
) -> float:
    if narration_duration_seconds <= 0:
        raise MediaError("Narration audio has no measurable duration.")
    timeline_duration = timeline_frames / fps
    difference = abs(narration_duration_seconds - timeline_duration)
    if difference > tolerance_seconds:
        raise MediaError(
            f"Narration is {narration_duration_seconds:.2f}s but the approved visual "
            f"timeline is {timeline_duration:.2f}s. Difference: {difference:.2f}s "
            f"(maximum {tolerance_seconds:.2f}s). Regenerate the storyboard from the "
            "current narration before rendering."
        )
    return timeline_duration


def render_documentary(
    job_id: str,
    manifest: TimelineManifest,
    project_root: str | Path | None = None,
    timeout_seconds: int = 3600,
) -> tuple[Path, MediaReport]:
    """Render an approved timeline to MP4 and run FFprobe quality checks."""
    root = Path(project_root or Path(__file__).resolve().parents[2]).resolve()
    renderer_dir = root / "renderer"
    remotion = renderer_dir / "node_modules" / ".bin" / "remotion"
    if not remotion.is_file():
        raise MediaError("Remotion is not installed. Run npm install inside the renderer directory.")
    if not manifest.narration_file:
        raise MediaError("A narration audio file is required before documentary rendering.")

    for scene in manifest.scenes:
        if scene.asset:
            _public_asset(renderer_dir, scene.asset.local_file)
    narration_path = _public_asset(renderer_dir, manifest.narration_file)
    narration_report = probe_media(narration_path)
    if not narration_report.audio_codec:
        raise MediaError("The narration file does not contain an audio stream.")
    expected_duration = _validate_narration_alignment(
        narration_report.duration_seconds,
        sum(scene.duration_frames for scene in manifest.scenes),
        manifest.fps,
    )
    if manifest.music_file:
        _public_asset(renderer_dir, manifest.music_file)

    props = manifest.to_remotion_props()
    generated_dir = renderer_dir / ".generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    props_path = generated_dir / f"{job_id}.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    output_dir = root / "renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{job_id}.mp4"
    command = [
        str(remotion),
        "render",
        "src/index.ts",
        "Documentary",
        str(output_path),
        f"--props={props_path}",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=renderer_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Remotion render exceeded the configured time limit.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout)[-3000:]
        raise MediaError(f"Remotion render failed: {detail}")
    report = validate_render(
        output_path,
        min_duration_seconds=3,
        max_duration_seconds=1800,
        require_audio=True,
        expected_width=manifest.width,
        expected_height=manifest.height,
        expected_duration_seconds=expected_duration,
    )
    return output_path, report
