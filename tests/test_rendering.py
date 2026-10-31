from pathlib import Path

import pytest

from jackpockets.media import MediaError
from jackpockets.rendering import _public_asset


def test_public_asset_rejects_path_traversal(tmp_path: Path) -> None:
    renderer = tmp_path / "renderer"
    public = renderer / "public"
    public.mkdir(parents=True)
    outside = tmp_path / "secret.txt"
    outside.write_text("no")
    with pytest.raises(MediaError, match="escapes"):
        _public_asset(renderer, "../secret.txt")


def test_public_asset_requires_existing_file(tmp_path: Path) -> None:
    renderer = tmp_path / "renderer"
    (renderer / "public").mkdir(parents=True)
    with pytest.raises(MediaError, match="missing"):
        _public_asset(renderer, "assets/missing.mp4")
