from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from openai import OpenAI, OpenAIError

from app.config import Settings, get_settings


def synthesize_speech_bytes(text: str) -> bytes:
    settings = get_settings()
    providers = _provider_order(settings.audio_tts_provider, settings)
    errors = []
    for provider in providers:
        try:
            if provider == "cartesia":
                return _synthesize_with_cartesia(text, settings)
            if provider == "deepgram":
                return _synthesize_with_deepgram(text, settings)
            if provider == "openai":
                return _synthesize_with_openai_bytes(text, settings)
        except RuntimeError as exc:
            errors.append(str(exc))
            if not settings.audio_fallback_enabled:
                break
    raise RuntimeError("Speech synthesis failed. " + " | ".join(errors))


def speech_media_type() -> str:
    settings = get_settings()
    provider = (settings.audio_tts_provider or "auto").strip().lower()
    if provider == "auto":
        provider = _provider_order("auto", settings)[0]
    if provider == "cartesia" and settings.cartesia_tts_container.lower() == "wav":
        return "audio/wav"
    if provider == "deepgram" and settings.deepgram_tts_encoding.lower() == "wav":
        return "audio/wav"
    return "audio/mpeg"


def _provider_order(requested_provider: str, settings: Settings) -> list[str]:
    provider = (requested_provider or "auto").strip().lower()
    if provider == "auto":
        if settings.cartesia_api_key:
            primary = "cartesia"
        elif settings.deepgram_api_key:
            primary = "deepgram"
        else:
            primary = "openai"
    elif provider in {"cartesia", "deepgram", "openai"}:
        primary = provider
    else:
        raise RuntimeError(f"Unsupported TTS provider: {requested_provider}")
    fallback_order = [item for item in ["cartesia", "deepgram", "openai"] if item != primary]
    if settings.audio_fallback_enabled:
        return [primary, *fallback_order]
    return [primary]


def _synthesize_with_cartesia(text: str, settings: Settings) -> bytes:
    if not settings.cartesia_api_key:
        raise RuntimeError("CARTESIA_API_KEY is not set. Cannot synthesize speech with Cartesia.")

    output_format = {"container": settings.cartesia_tts_container}
    if settings.cartesia_tts_container.lower() == "wav":
        output_format["encoding"] = settings.cartesia_tts_encoding
        output_format["sample_rate"] = settings.cartesia_tts_sample_rate

    request = Request(
        "https://api.cartesia.ai/tts/bytes",
        data=json.dumps(
            {
                "model_id": settings.cartesia_tts_model,
                "transcript": text,
                "voice": {"mode": "id", "id": settings.cartesia_tts_voice_id},
                "output_format": output_format,
            }
        ).encode("utf-8"),
        headers={
            "X-API-Key": settings.cartesia_api_key,
            "Cartesia-Version": settings.cartesia_api_version,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.cartesia_timeout_seconds) as response:
            return response.read()
    except (OSError, URLError) as exc:
        raise RuntimeError(f"Cartesia speech synthesis failed: {exc}") from exc


def _synthesize_with_deepgram(text: str, settings: Settings) -> bytes:
    if not settings.deepgram_api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is not set. Cannot synthesize speech with Deepgram.")

    query = urlencode({"model": settings.deepgram_tts_model, "encoding": settings.deepgram_tts_encoding})
    request = Request(
        f"https://api.deepgram.com/v1/speak?{query}",
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={
            "Authorization": f"Token {settings.deepgram_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.deepgram_timeout_seconds) as response:
            return response.read()
    except (OSError, URLError) as exc:
        raise RuntimeError(f"Deepgram speech synthesis failed: {exc}") from exc


def _synthesize_with_openai_bytes(text: str, settings: Settings) -> bytes:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Cannot synthesize speech with OpenAI.")
    client = OpenAI(api_key=settings.openai_api_key)
    try:
        with client.audio.speech.with_streaming_response.create(
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            input=text,
            speed=settings.openai_tts_speed,
        ) as response:
            return response.read()
    except OpenAIError as exc:
        raise RuntimeError(f"OpenAI speech synthesis failed: {exc}") from exc


def synthesize_speech(text: str, output_path: str) -> str:
    settings = get_settings()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(synthesize_speech_bytes(text))
        return str(path)
    except RuntimeError:
        print(text)
        raise
