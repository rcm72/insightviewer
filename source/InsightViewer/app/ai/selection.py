from __future__ import annotations

from dataclasses import asdict
from typing import Any

from flask import Request

from .types import ModelSelection, ProviderId


COOKIE_PROVIDER = "ai_provider"
COOKIE_MODEL = "ai_model"


def default_selection() -> ModelSelection:
    return ModelSelection(provider="openai", model="gpt-4o-mini")


def get_selection_from_request(req: Request) -> ModelSelection:
    provider = (req.cookies.get(COOKIE_PROVIDER) or "").strip().lower()
    model = (req.cookies.get(COOKIE_MODEL) or "").strip()

    if provider not in ("openai", "ollama"):
        return default_selection()
    if not model:
        return default_selection()
    return ModelSelection(provider=provider, model=model)  # type: ignore[arg-type]


def validate_selection(selection: ModelSelection, provider_models: dict[ProviderId, list[str]]) -> ModelSelection:
    models = provider_models.get(selection.provider) or []
    if selection.model in models:
        return selection
    # fall back to first model for that provider, otherwise global default
    if models:
        return ModelSelection(provider=selection.provider, model=models[0])
    return default_selection()


def selection_to_json(selection: ModelSelection) -> dict[str, Any]:
    return asdict(selection)

