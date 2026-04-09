from __future__ import annotations

from typing import Any

import requests

from ..errors import ProviderConfigError, ProviderRequestError, ProviderResponseError
from ..types import ChatRequest, ChatResponse, EmbedRequest, EmbedResponse
from .base import AIProvider


class OllamaProvider(AIProvider):
    id = "ollama"

    def __init__(self, base_url: str | None, auth_token: str | None = None):
        self._base_url = (base_url or "").rstrip("/")
        self._auth = auth_token
        if not self._base_url:
            raise ProviderConfigError("OLLAMA.BASE not configured")

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._auth:
            headers["Authorization"] = f"Bearer {self._auth}"
        return headers

    def chat(self, req: ChatRequest) -> ChatResponse:
        # Using /api/generate for compatibility with existing codebase scripts.
        url = f"{self._base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": req.model,
            "prompt": f"{req.system}\n\n{req.user}".strip(),
            "stream": False,
            "options": {
                "temperature": float(req.temperature),
            },
        }
        try:
            r = requests.post(url, json=payload, headers=self._headers(), timeout=60)
        except requests.RequestException as e:
            raise ProviderRequestError(f"Ollama request failed: {e}") from e

        if not r.ok:
            raise ProviderRequestError(f"Ollama HTTP {r.status_code}: {r.text[:5000]}")

        try:
            body = r.json()
        except Exception as e:
            raise ProviderResponseError(f"Ollama response JSON parse failed: {e}") from e

        # Typical response: { "response": "...", ... }
        text = body.get("response")
        if not isinstance(text, str):
            raise ProviderResponseError("Ollama response missing 'response' string")

        return ChatResponse(text=text, raw=body)

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        # Try common endpoints/param shapes used by different Ollama versions/clients.
        endpoints = ["/api/embeddings", "/api/embed", "/api/embeds"]
        payloads = [
            {"model": req.model, "prompt": req.text},
            {"model": req.model, "input": req.text},
            {"model": req.model, "text": req.text},
        ]

        last_err: str | None = None
        for ep in endpoints:
            url = f"{self._base_url}{ep}"
            for payload in payloads:
                try:
                    r = requests.post(url, json=payload, headers=self._headers(), timeout=60)
                except requests.RequestException as e:
                    last_err = str(e)
                    continue

                if not r.ok:
                    last_err = f"{r.status_code} {r.text}"
                    continue

                try:
                    body = r.json()
                except Exception as e:
                    last_err = str(e)
                    continue

                emb = None
                if isinstance(body, dict):
                    if isinstance(body.get("embedding"), list):
                        emb = body["embedding"]
                    elif isinstance(body.get("embeddings"), list) and body["embeddings"]:
                        first = body["embeddings"][0]
                        if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                            emb = first["embedding"]
                        elif isinstance(first, list):
                            emb = first
                    elif isinstance(body.get("data"), list) and body["data"]:
                        d0 = body["data"][0]
                        if isinstance(d0, dict) and isinstance(d0.get("embedding"), list):
                            emb = d0["embedding"]

                if isinstance(emb, list) and emb and all(isinstance(x, (int, float)) for x in emb[:10]):
                    return EmbedResponse(embedding=[float(x) for x in emb], raw=body)

        raise ProviderRequestError(f"Failed to obtain embedding from Ollama. Last error: {last_err}")

