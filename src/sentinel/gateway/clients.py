"""LLMClient interface — thin wrapper so Anthropic/OpenAI/vLLM are drop-in (blueprint §2). Phase P1
stub; full token/cost accounting lands with the gateway app in Phase P5.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMClient(ABC):
    @abstractmethod
    def complete(self, *, system: str, messages: list[dict], model: str, max_tokens: int) -> LLMResponse:
        raise NotImplementedError


class AnthropicLLMClient(LLMClient):
    """Primary LLM client (blueprint §2). Imports the anthropic SDK lazily inside complete() so this
    module stays importable without an API key configured (CLAUDE.md: offline-runnable core)."""

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key

    def complete(self, *, system: str, messages: list[dict], model: str, max_tokens: int) -> LLMResponse:
        raise NotImplementedError(
            "gateway.clients.AnthropicLLMClient.complete is Phase P1 work. "
            "See ARCHITECTURE_BLUEPRINT.md §2, §8."
        )
