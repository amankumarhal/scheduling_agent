from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.5", alias="OPENAI_MODEL")
    audio_stt_provider: str = Field(default="auto", alias="AUDIO_STT_PROVIDER")
    audio_tts_provider: str = Field(default="auto", alias="AUDIO_TTS_PROVIDER")
    audio_fallback_enabled: bool = Field(default=True, alias="AUDIO_FALLBACK_ENABLED")
    openai_stt_model: str = Field(default="gpt-4o-mini-transcribe", alias="OPENAI_STT_MODEL")
    openai_tts_model: str = Field(default="gpt-4o-mini-tts", alias="OPENAI_TTS_MODEL")
    openai_tts_voice: str = Field(default="alloy", alias="OPENAI_TTS_VOICE")
    openai_tts_speed: float = Field(default=1.25, ge=0.25, le=4.0, alias="OPENAI_TTS_SPEED")
    deepgram_api_key: str | None = Field(default=None, alias="DEEPGRAM_API_KEY")
    deepgram_stt_model: str = Field(default="nova-3", alias="DEEPGRAM_STT_MODEL")
    deepgram_tts_model: str = Field(default="aura-2-thalia-en", alias="DEEPGRAM_TTS_MODEL")
    deepgram_tts_encoding: str = Field(default="mp3", alias="DEEPGRAM_TTS_ENCODING")
    deepgram_timeout_seconds: float = Field(default=12.0, ge=1.0, le=60.0, alias="DEEPGRAM_TIMEOUT_SECONDS")
    session_log_dir: str = Field(default="logs/sessions", alias="SESSION_LOG_DIR")
    appointment_data_dir: str = Field(default="data", alias="APPOINTMENT_DATA_DIR")
    debug: bool = Field(default=False, alias="DEBUG")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
