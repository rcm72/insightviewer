from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import load_config
from .errors import ProviderConfigError
from .providers import OllamaProvider, OpenAIProvider
from .types import ProviderId


def _split_csv(s: str | None) -> list[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


@dataclass(frozen=True)
class ProviderInfo:
    id: ProviderId
    label: str
    models: list[str]


class ProviderRegistry:
    """
    Single place to construct providers and list model options.
    """

    def __init__(self):
        self._cfg = load_config()

        # Defaults
        self._openai_models = _split_csv(self._cfg.get("OPENAI", "MODELS", fallback="")) or [
            "gpt-4o-mini",
            "gpt-4.1-mini",
        ]
        self._ollama_models = _split_csv(self._cfg.get("OLLAMA", "MODELS", fallback="")) or [
            self._cfg.get("OLLAMA", "MODEL", fallback="qwen2.5:14b")
        ]

        self._ollama_base = self._cfg.get("OLLAMA", "BASE", fallback=None)
        self._ollama_auth = (self._cfg.get("OLLAMA", "AUTH", fallback=None) or None)

    def list_providers(self) -> list[ProviderInfo]:
        out: list[ProviderInfo] = []
        out.append(ProviderInfo(id="openai", label="OpenAI", models=self._openai_models))
        out.append(ProviderInfo(id="ollama", label="Ollama", models=self._ollama_models))
        return out

    def get_provider(self, provider_id: ProviderId):
        if provider_id == "openai":
            return OpenAIProvider()
        if provider_id == "ollama":
            if not self._ollama_base:
                raise ProviderConfigError("OLLAMA.BASE not configured in config.ini")
            return OllamaProvider(base_url=self._ollama_base, auth_token=self._ollama_auth)
        raise ProviderConfigError(f"Unknown provider: {provider_id}")

