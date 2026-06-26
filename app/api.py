from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.orchestrator import AppointmentOrchestrator
from app.stt_client import transcribe_audio
from app.tts_client import synthesize_speech

app = FastAPI(title="Appointment Scheduling AI Agent")
agent = AppointmentOrchestrator()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Appointment Scheduling AI Agent</title>
        <style>
          body {
            margin: 0;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: #1f2937;
            background: #f8fafc;
          }
          main {
            max-width: 760px;
            margin: 56px auto;
            padding: 0 24px;
          }
          h1 {
            font-size: 32px;
            margin-bottom: 8px;
          }
          p {
            line-height: 1.55;
          }
          code {
            background: #e5e7eb;
            padding: 2px 6px;
            border-radius: 6px;
          }
          .links {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 24px;
          }
          a {
            color: #0f766e;
            font-weight: 650;
          }
        </style>
      </head>
      <body>
        <main>
          <h1>Appointment Scheduling AI Agent</h1>
          <p>The FastAPI server is running. Use the API docs to try chat requests from your browser.</p>
          <p>Available endpoints: <code>GET /health</code>, <code>POST /chat</code>, and <code>POST /voice</code>.</p>
          <div class="links">
            <a href="/docs">Open API Docs</a>
            <a href="/health">Health Check</a>
          </div>
        </main>
      </body>
    </html>
    """


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    response = agent.handle_message(request.message, session_id=request.session_id)
    return response.model_dump(mode="json")


@app.post("/voice")
async def voice(
    audio: UploadFile = File(...),
    session_id: str = Form(default="default"),
    tts_output_path: str | None = Form(default=None),
) -> dict:
    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
        temp_audio.write(await audio.read())
        temp_audio_path = temp_audio.name

    transcription = transcribe_audio(temp_audio_path)
    response = agent.handle_message(transcription, session_id=session_id)
    output_path = tts_output_path
    if output_path:
        synthesize_speech(response.message, output_path)

    return {
        "transcription": transcription,
        "response": response.model_dump(mode="json"),
        "tts_output_path": output_path,
    }
