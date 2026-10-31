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
