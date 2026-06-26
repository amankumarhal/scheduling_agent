from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings


def test_root_serves_interactive_ui() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "messageInput" in response.text
    assert "Hold to talk" in response.text
    assert "Interrupt" in response.text
    assert "showGreeting({ spoken: true })" in response.text
    assert 'id="status"' in response.text
    assert response.text.count('id="status"') == 1
    assert "shouldSkipDuplicateAssistant" in response.text
    assert "speakWithStream" in response.text
    assert "/speak/stream" in response.text


def test_stream_endpoint_returns_sse() -> None:
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"session_id": "stream-test", "message": "I have severe chest pain."},
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status_code == 200
    assert "event: delta" in body
    assert "event: final" in body
    assert "emergencies" in body


def test_speak_stream_requires_cartesia_streaming(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TTS_PROVIDER", "openai")
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)
    response = client.post("/speak/stream", json={"text": "Hello"})
    assert response.status_code == 409
