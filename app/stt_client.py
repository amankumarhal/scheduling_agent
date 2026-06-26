from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from openai import OpenAI, OpenAIError

from app.config import Settings, get_settings


def transcribe_audio(file_path: str) -> str:
    settings = get_settings()
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    providers = _provider_order(settings.audio_stt_provider, settings)
    errors = []
    for provider in providers:
        try:
            if provider == "deepgram":
                return _transcribe_with_deepgram(path, settings)
            if provider == "openai":
                return _transcribe_with_openai(path, settings)
        except RuntimeError as exc:
            errors.append(str(exc))
            if not settings.audio_fallback_enabled:
                break
    raise RuntimeError("Transcription failed. " + " | ".join(errors))


def _provider_order(requested_provider: str, settings: Settings) -> list[str]:
    provider = (requested_provider or "auto").strip().lower()
    if provider == "auto":
        primary = "deepgram" if settings.deepgram_api_key else "openai"
    elif provider in {"deepgram", "openai"}:
        primary = provider
    else:
        raise RuntimeError(f"Unsupported STT provider: {requested_provider}")
    fallback = "openai" if primary == "deepgram" else "deepgram"
    if settings.audio_fallback_enabled:
        return [primary, fallback]
    return [primary]


def _transcribe_with_deepgram(path: Path, settings: Settings) -> str:
    if not settings.deepgram_api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is not set. Cannot transcribe audio with Deepgram.")

    query = urlencode({"model": settings.deepgram_stt_model, "language": "en", "smart_format": "true"})
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    request = Request(
        f"https://api.deepgram.com/v1/listen?{query}",
        data=path.read_bytes(),
        headers={
            "Authorization": f"Token {settings.deepgram_api_key}",
            "Content-Type": content_type,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.deepgram_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Deepgram transcription failed: {exc}") from exc

    try:
        transcript = payload["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Deepgram transcription response did not include a transcript.") from exc
    return str(transcript).strip()


def _transcribe_with_openai(path: Path, settings: Settings) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Cannot transcribe audio with OpenAI.")

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
