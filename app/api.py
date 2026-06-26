from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, UploadFile
from pydantic import BaseModel

from app.orchestrator import AppointmentOrchestrator
from app.stt_client import transcribe_audio
from app.tts_client import synthesize_speech

app = FastAPI(title="Appointment Scheduling AI Agent")
agent = AppointmentOrchestrator()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


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

