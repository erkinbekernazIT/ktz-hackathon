from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any

from src.infrastructure.llm.config import (
    GROQ_API_KEY_ENV,
    GROQ_BASE_URL,
    GROQ_DEFAULT_MODEL,
    LLM_MAX_RETRIES,
    LLM_RETRY_BASE_DELAY_SEC,
)

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the LLM provider fails after retries."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class LLMClient(ABC):
    """Abstract LLM client used by AI agents."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_json: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Return the model text completion for the given prompt."""
        ...


class LLMClientStub(LLMClient):
    """Deterministic stub — no network calls. Useful for tests / offline MVP."""

    def __init__(self, response: str = "STUB_RESPONSE") -> None:
        self._response = response

    def complete(
        self,
        prompt: str,  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        response_json: bool = False,  # noqa: ARG002
        temperature: float = 0.2,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
    ) -> str:
        return self._response


class GroqLLMClient(LLMClient):
    """LLM client backed by Groq's OpenAI-compatible Chat Completions API.

    Requires ``GROQ_API_KEY`` in the environment (or an explicit ``api_key``).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = GROQ_BASE_URL,
        model: str = GROQ_DEFAULT_MODEL,
        max_retries: int = LLM_MAX_RETRIES,
        retry_base_delay: float = LLM_RETRY_BASE_DELAY_SEC,
    ) -> None:
        key = api_key or os.environ.get(GROQ_API_KEY_ENV)
        if not key:
            raise LLMError(
                f"Groq API key not set. Export {GROQ_API_KEY_ENV} or pass api_key=..."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError(
                "The 'openai' package is required for GroqLLMClient. "
                "Install it with: pip install openai"
            ) from exc

        self._client = OpenAI(api_key=key, base_url=base_url)
        self._model = model
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_json: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_json:
            kwargs["response_format"] = {"type": "json_object"}

        last_error: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content
                if content is None:
                    raise LLMError("Groq returned an empty completion")
                return content
            except LLMError:
                raise
            except Exception as exc:  # noqa: BLE001 — provider SDK errors vary
                last_error = exc
                if attempt + 1 >= self._max_retries:
                    break
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Groq LLM call failed (attempt %d/%d): %s; retrying in %.1fs",
                    attempt + 1,
                    self._max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)

        raise LLMError(
            f"Groq LLM call failed after {self._max_retries} attempts: {last_error}",
            cause=last_error,
        )


def create_llm_client(
    *,
    use_stub: bool | None = None,
    api_key: str | None = None,
) -> LLMClient:
    """Factory: Groq client when a key is available, otherwise stub.

    Args:
        use_stub: Force stub (True) or Groq (False). ``None`` → auto-detect
                  from ``GROQ_API_KEY`` / ``api_key``.
        api_key: Optional explicit Groq API key.
    """
    if use_stub is True:
        return LLMClientStub()

    key = api_key or os.environ.get(GROQ_API_KEY_ENV)
    if use_stub is False:
        return GroqLLMClient(api_key=key)

    if key:
        return GroqLLMClient(api_key=key)

    logger.info(
        "No %s set — using LLMClientStub. Set the env var to enable Groq.",
        GROQ_API_KEY_ENV,
    )
    return LLMClientStub()
