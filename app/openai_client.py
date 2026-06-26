from __future__ import annotations

from typing import Any, AsyncGenerator

from openai import AsyncOpenAI, OpenAI, OpenAIError

from app.config import get_settings


class OpenAIClientError(RuntimeError):
    """Raised when the OpenAI adapter cannot complete an LLM call."""
    pass


class OpenAIClient:
    """Small SDK adapter so business logic does not depend on OpenAI SDK details."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Store model and API-key configuration without creating SDK clients yet."""
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self._client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Create and reuse the synchronous OpenAI SDK client lazily."""
        if not self.api_key:
            raise OpenAIClientError(
                "OPENAI_API_KEY is not set. Add it to your environment or .env file before calling the LLM."
            )
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    @property
    def async_client(self) -> AsyncOpenAI:
        """Create and reuse the async OpenAI SDK client lazily."""
        if not self.api_key:
            raise OpenAIClientError(
                "OPENAI_API_KEY is not set. Add it to your environment or .env file before calling the LLM."
            )
        if self._async_client is None:
            self._async_client = AsyncOpenAI(api_key=self.api_key)
        return self._async_client

    def call_llm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> Any:
        """Call the configured chat model with optional strict tool schemas."""
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

    async def stream_llm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream the LLM response, yielding content deltas then assembled tool calls."""
        try:
            stream = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice if tools else None,
                stream=True,
            )
            accumulated_tool_calls: dict[int, dict[str, Any]] = {}
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    yield {"type": "content", "text": delta.content}
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc.id:
                            accumulated_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                accumulated_tool_calls[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                accumulated_tool_calls[idx]["function"]["arguments"] += tc.function.arguments
                if choice.finish_reason == "tool_calls":
                    tool_calls_list = [accumulated_tool_calls[i] for i in sorted(accumulated_tool_calls.keys())]
                    yield {"type": "tool_calls", "tool_calls": tool_calls_list}
                    accumulated_tool_calls = {}
        except OpenAIClientError:
            raise
        except OpenAIError as exc:
            raise OpenAIClientError(f"OpenAI LLM stream failed: {exc}") from exc
