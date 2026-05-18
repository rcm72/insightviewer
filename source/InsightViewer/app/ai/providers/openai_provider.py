from __future__ import annotations

import os
from typing import Any

import requests

from ..errors import ProviderConfigError, ProviderRequestError, ProviderResponseError
from ..types import ChatRequest, ChatResponse
from .base import AIProvider


class OpenAIProvider(AIProvider):
    id = "openai"

    def __init__(self, api_key: str | None = None, base_url: str = "https://api.openai.com"):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        if not self._api_key:
            raise ProviderConfigError("OPENAI_API_KEY not set in environment")

    # Models that require max_completion_tokens instead of max_tokens
    _MAX_COMPLETION_TOKENS_MODELS = ("o1", "o3", "o4", "gpt-5")

    def _uses_max_completion_tokens(self, model: str) -> bool:
        return any(model.startswith(prefix) for prefix in self._MAX_COMPLETION_TOKENS_MODELS)

    # Reasoning models consume tokens internally before writing output.
    # Use a much higher limit so there are tokens left for the actual response.
    _REASONING_MIN_TOKENS = 16000

    def chat(self, req: ChatRequest) -> ChatResponse:
        url = f"{self._base_url}/v1/chat/completions"
        use_new_params = self._uses_max_completion_tokens(req.model)
        tokens_key = "max_completion_tokens" if use_new_params else "max_tokens"
        token_limit = int(req.max_tokens)
        if use_new_params and token_limit < self._REASONING_MIN_TOKENS:
            token_limit = self._REASONING_MIN_TOKENS
        payload: dict[str, Any] = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            tokens_key: token_limit,
        }
        if not use_new_params:
            payload["temperature"] = float(req.temperature)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        timeout = 180 if use_new_params else 45
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            raise ProviderRequestError(f"OpenAI request failed: {e}") from e

        # Keep error messages secret-safe (no key), include status code and response text.
        if not r.ok:
            raise ProviderRequestError(f"OpenAI HTTP {r.status_code}: {r.text[:5000]}")

        try:
            body = r.json()
        except Exception as e:
            raise ProviderResponseError(f"OpenAI response JSON parse failed: {e}") from e

        try:
            content = body["choices"][0]["message"]["content"]
        except Exception as e:
            raise ProviderResponseError(f"OpenAI response shape unexpected: {e}. Body: {str(body)[:2000]}") from e

        # Some models (o-series, gpt-5) may return None for content when reasoning
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ProviderResponseError(f"OpenAI content unexpected type {type(content)}: {str(content)[:500]}")

        return ChatResponse(text=content, raw=body)

