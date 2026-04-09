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

    def chat(self, req: ChatRequest) -> ChatResponse:
        url = f"{self._base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "temperature": float(req.temperature),
            "max_tokens": int(req.max_tokens),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=45)
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
            raise ProviderResponseError(f"OpenAI response shape unexpected: {e}") from e

        if not isinstance(content, str):
            raise ProviderResponseError("OpenAI content not a string")

        return ChatResponse(text=content, raw=body)

