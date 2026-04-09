from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import ChatRequest, ChatResponse, EmbedRequest, EmbedResponse, ProviderId


class AIProvider(ABC):
    id: ProviderId

    @abstractmethod
    def chat(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError("Embeddings not supported by this provider")

