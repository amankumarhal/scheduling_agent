from fastapi.testclient import TestClient

from app.api import app


def test_root_serves_interactive_ui() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "messageInput" in response.text
    assert "Hold to talk" in response.text
    assert "Interrupt" in response.text


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
