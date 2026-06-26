from __future__ import annotations

from typing import Any

from openai import OpenAI, OpenAIError

from app.config import get_settings


class OpenAIClientError(RuntimeError):
    pass


class OpenAIClient:
    """Small SDK adapter so business logic does not depend on OpenAI SDK details."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if not self.api_key:
            raise OpenAIClientError(
                "OPENAI_API_KEY is not set. Add it to your environment or .env file before calling the LLM."
            )
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def call_llm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> Any:
        try:
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice if tools else None,
            )
        except OpenAIClientError:
            raise
        except OpenAIError as exc:
            raise OpenAIClientError(f"OpenAI LLM call failed: {exc}") from exc

