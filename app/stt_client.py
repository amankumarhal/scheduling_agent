from __future__ import annotations

from pathlib import Path

from openai import OpenAI, OpenAIError

from app.config import get_settings


def transcribe_audio(file_path: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Cannot transcribe audio.")
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        with path.open("rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model=settings.openai_stt_model,
                file=audio_file,
                language="en",
            )
        return getattr(transcript, "text", str(transcript))
    except OpenAIError as exc:
        raise RuntimeError(f"OpenAI transcription failed: {exc}") from exc
