import asyncio

import pytest

from jackpockets.narration import NarrationError, synthesize_narration


def test_empty_script_is_rejected_before_speech_service_call(tmp_path) -> None:
    with pytest.raises(NarrationError, match="cannot be empty"):
        asyncio.run(synthesize_narration("  ", tmp_path / "voice.mp3"))


def test_word_boundaries_are_grouped_into_readable_phrases() -> None:
    from jackpockets.narration import WordCaption, group_word_captions

    words = [
        WordCaption(0, 8, "The"),
        WordCaption(9, 17, "story"),
        WordCaption(18, 26, "starts"),
        WordCaption(27, 35, "here."),
        WordCaption(40, 48, "Then"),
        WordCaption(49, 57, "it"),
        WordCaption(58, 66, "continues"),
    ]
    captions = group_word_captions(words, fps=30)
    assert captions[0].text == "The story starts here."
    assert captions[0].start_frame == 0
    assert captions[0].end_frame == 35
    assert captions[1].text == "Then it continues"



def test_missing_word_boundaries_can_use_estimated_caption_timing() -> None:
    from jackpockets.narration import estimate_word_captions, group_word_captions

    words = estimate_word_captions(
        "The ocean cables connect continents.", duration_frames=900, fps=30
    )
    captions = group_word_captions(words, fps=30)

    assert words
    assert words[0].start_frame == 0
    assert words[-1].end_frame == 900
    assert " ".join(item.text for item in captions) == (
        "The ocean cables connect continents."
    )



def test_synthesis_falls_back_when_edge_tts_omits_word_boundaries(
    tmp_path, monkeypatch
) -> None:
    import sys
    from types import SimpleNamespace

    from jackpockets import narration

    class FakeCommunicate:
        def __init__(self, *args, **kwargs):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"fake-mp3-data"}

    monkeypatch.setitem(
        sys.modules, "edge_tts", SimpleNamespace(Communicate=FakeCommunicate)
    )
    monkeypatch.setattr(
        narration, "probe_audio_duration_frames", lambda _path, _fps: 90
    )

    result = asyncio.run(
        narration.synthesize_narration(
            "The ocean cables connect continents.", tmp_path / "voice.mp3"
        )
    )

    assert result.duration_frames == 90
    assert result.captions
    assert " ".join(item.text for item in result.captions) == (
        "The ocean cables connect continents."
    )
