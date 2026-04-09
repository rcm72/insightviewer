from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional


ProviderId = Literal["openai", "ollama"]


@dataclass(frozen=True)
class ModelSelection:
    provider: ProviderId
    model: str


@dataclass(frozen=True)
class ChatRequest:
    system: str
    user: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 2000


@dataclass(frozen=True)
class ChatResponse:
    text: str
    raw: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class EmbedRequest:
    text: str
    model: str


@dataclass(frozen=True)
class EmbedResponse:
    embedding: list[float]
    raw: Optional[dict[str, Any]] = None

