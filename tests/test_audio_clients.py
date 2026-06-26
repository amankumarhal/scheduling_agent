import json

from app.config import get_settings
from app.stt_client import transcribe_audio
from app.tts_client import speech_media_type, synthesize_speech_bytes


class StubHttpResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.payload


def reset_settings(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    monkeypatch.setenv("AUDIO_STT_PROVIDER", "deepgram")
    monkeypatch.setenv("AUDIO_TTS_PROVIDER", "deepgram")
    monkeypatch.setenv("AUDIO_FALLBACK_ENABLED", "false")


def test_deepgram_stt_transcribes_audio(monkeypatch, tmp_path) -> None:
    reset_settings(monkeypatch)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg_test")
    get_settings.cache_clear()
    audio_path = tmp_path / "voice.webm"
    audio_path.write_bytes(b"audio")

    def stub_urlopen(request, timeout):
        assert "api.deepgram.com/v1/listen" in request.full_url
        assert "language=en" in request.full_url
        return StubHttpResponse(
            json.dumps(
                {"results": {"channels": [{"alternatives": [{"transcript": "I need an appointment."}]}]}}
            ).encode("utf-8")
        )

    monkeypatch.setattr("app.stt_client.urlopen", stub_urlopen)

    assert transcribe_audio(str(audio_path)) == "I need an appointment."


def test_deepgram_tts_returns_audio_bytes(monkeypatch) -> None:
    reset_settings(monkeypatch)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg_test")
    get_settings.cache_clear()

    def stub_urlopen(request, timeout):
        assert "api.deepgram.com/v1/speak" in request.full_url
        body = json.loads(request.data.decode("utf-8"))
        assert body["text"] == "Hello"
        return StubHttpResponse(b"mp3-bytes")

    monkeypatch.setattr("app.tts_client.urlopen", stub_urlopen)

    assert synthesize_speech_bytes("Hello") == b"mp3-bytes"


def test_cartesia_tts_returns_audio_bytes(monkeypatch) -> None:
    reset_settings(monkeypatch)
    monkeypatch.setenv("AUDIO_TTS_PROVIDER", "cartesia")
    monkeypatch.setenv("CARTESIA_API_KEY", "cartesia_test")
    get_settings.cache_clear()

    def stub_urlopen(request, timeout):
        assert request.full_url == "https://api.cartesia.ai/tts/bytes"
        assert request.headers["Authorization"] == "Bearer cartesia_test"
        assert "Cartesia-version" in request.headers
        body = json.loads(request.data.decode("utf-8"))
        assert body["transcript"] == "Hello"
        assert body["model_id"] == "sonic-3.5"
        assert body["voice"]["mode"] == "id"
        assert body["output_format"]["container"] == "wav"
        return StubHttpResponse(b"wav-bytes")

    monkeypatch.setattr("app.tts_client.urlopen", stub_urlopen)

    assert synthesize_speech_bytes("Hello") == b"wav-bytes"
    assert speech_media_type() == "audio/wav"


def test_auto_tts_prefers_cartesia_when_key_exists(monkeypatch) -> None:
    reset_settings(monkeypatch)
    monkeypatch.setenv("AUDIO_TTS_PROVIDER", "auto")
    monkeypatch.setenv("CARTESIA_API_KEY", "cartesia_test")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg_test")
    get_settings.cache_clear()

    def stub_urlopen(request, timeout):
        assert request.full_url == "https://api.cartesia.ai/tts/bytes"
        return StubHttpResponse(b"cartesia-bytes")

    monkeypatch.setattr("app.tts_client.urlopen", stub_urlopen)

    assert synthesize_speech_bytes("Hello") == b"cartesia-bytes"
