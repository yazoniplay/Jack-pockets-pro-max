import asyncio

import pytest

from jackpockets.narration import NarrationError, synthesize_narration


def test_empty_script_is_rejected_before_speech_service_call(tmp_path) -> None:
    with pytest.raises(NarrationError, match="cannot be empty"):
        asyncio.run(synthesize_narration("  ", tmp_path / "voice.mp3"))
