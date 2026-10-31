from jackpockets.assets import choose_video_file


def test_choose_video_file_prefers_high_resolution_mp4() -> None:
    files = [
        {"file_type": "video/mp4", "width": 640, "height": 360, "link": "https://videos.pexels.com/low.mp4"},
        {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://videos.pexels.com/high.mp4"},
        {"file_type": "video/webm", "width": 3840, "height": 2160, "link": "https://videos.pexels.com/high.webm"},
    ]
    selected = choose_video_file(files)
    assert selected is not None
    assert selected["width"] == 1920


def test_choose_video_file_returns_none_without_mp4() -> None:
    assert choose_video_file([{"file_type": "video/webm", "link": "https://example.com/a.webm"}]) is None
