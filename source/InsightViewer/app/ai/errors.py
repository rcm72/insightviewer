from __future__ import annotations


class AIError(RuntimeError):
    """Base error for AI module (no secrets in messages)."""


class ProviderConfigError(AIError):
    pass


class ProviderRequestError(AIError):
    pass


class ProviderResponseError(AIError):
    pass

