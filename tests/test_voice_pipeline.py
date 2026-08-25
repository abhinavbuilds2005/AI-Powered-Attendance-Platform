import pytest

from src.pipelines.voice_pipeline import safe_get_voice_embedding


def test_empty_audio_returns_none_and_clear_message():
    embedding, message = safe_get_voice_embedding(None)
    assert embedding is None
    assert "No voice sample" in message


def test_bad_audio_data_returns_none_and_clear_message():
    embedding, message = safe_get_voice_embedding('not-valid-base64')
    assert embedding is None
    assert "voice sample" in message.lower()
