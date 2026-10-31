from pathlib import Path

import pytest

from jackpockets.media import MediaError, probe_media


def test_probe_media_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(MediaError, match="does not exist"):
        probe_media(tmp_path / "missing.mp4")
