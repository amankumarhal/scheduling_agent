from __future__ import annotations

from pathlib import Path

from openai import OpenAI, OpenAIError

from app.config import get_settings


def synthesize_speech(text: str, output_path: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        print(text)
        return output_path

    client = OpenAI(api_key=settings.openai_api_key)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = client.audio.speech.create(
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            input=text,
        )
        response.stream_to_file(path)
        return str(path)
    except OpenAIError as exc:
        print(text)
        raise RuntimeError(f"OpenAI speech synthesis failed: {exc}") from exc

