"""LLMClient interface + token/cost accounting (blueprint §2, §11 "cost blowup" mitigation).

Thin on purpose so Anthropic / OpenAI / vLLM are drop-in. Four pieces:

* AnthropicLLMClient -- the real client. Imports the `anthropic` SDK lazily inside complete(), so the
  core stays importable with no SDK credentials (CLAUDE.md: offline-runnable core).
* ScriptedLLMClient  -- replays canned responses; for tests and deterministic demos.
* CachingLLMClient   -- wraps any client with an on-disk cache keyed by the full request, so eval
  reruns are free and byte-identical (blueprint §11: "offline caching of agent proposals").
* UsageLedger        -- per-component token/cost accounting. The agent and the verifier each get
  their OWN ledger -- CLAUDE.md: they must not share state.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str = ""
    cost_known: bool = True
    cached: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def price_usd(model: str, input_tokens: int, output_tokens: int, pricing: dict) -> tuple[float, bool]:
    """(cost, known). `pricing` is config `pricing_usd_per_mtok`; unknown models cost 0, known=False."""
    rates = pricing.get(model)
    if not rates:
        return 0.0, False
    cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    return round(cost, 8), True


@dataclass
class UsageLedger:
    """Accumulates usage for one component (agent OR verifier -- never shared between them)."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cost_known: bool = True
    cached_calls: int = 0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def record(self, response: LLMResponse) -> None:
        self.calls += 1
        self.cached_calls += int(response.cached)
        self.input_tokens += response.input_tokens
        self.output_tokens += response.output_tokens
        self.cost_usd = round(self.cost_usd + response.cost_usd, 8)
        self.cost_known = self.cost_known and response.cost_known
        per = self.by_model.setdefault(
            response.model or "unknown", {"calls": 0, "tokens": 0, "cost_usd": 0.0}
        )
        per["calls"] += 1
        per["tokens"] += response.total_tokens
        per["cost_usd"] = round(per["cost_usd"] + response.cost_usd, 8)

    def snapshot(self) -> dict:
        return {**asdict(self), "total_tokens": self.total_tokens}


class LLMClient(ABC):
    @abstractmethod
    def complete(self, *, system: str, messages: list[dict], model: str, max_tokens: int) -> LLMResponse:
        raise NotImplementedError


class AnthropicLLMClient(LLMClient):
    """Primary LLM client (blueprint §2). Credentials resolve the SDK's usual way (ANTHROPIC_API_KEY,
    ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile)."""

    def __init__(self, *, api_key: str | None = None, pricing: dict | None = None) -> None:
        self._api_key = api_key
        self._pricing = pricing or {}
        self._client = None

    def _sdk(self):
        if self._client is None:
            import anthropic  # lazy: keep the core importable offline

            self._client = (
                anthropic.Anthropic(api_key=self._api_key) if self._api_key else anthropic.Anthropic()
            )
        return self._client

    def complete(self, *, system: str, messages: list[dict], model: str, max_tokens: int) -> LLMResponse:
        response = self._sdk().messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=messages
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"model {model} declined the request (stop_reason=refusal)")
        text = "".join(block.text for block in response.content if block.type == "text")
        cost, known = price_usd(
            model, response.usage.input_tokens, response.usage.output_tokens, self._pricing
        )
        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
            model=model,
            cost_known=known,
        )


class ScriptedLLMClient(LLMClient):
    """Returns canned texts in order; token counts are estimated (~4 chars/token). Records every
    request in `.requests` so tests can assert what the agent actually sent."""

    def __init__(self, responses: Iterable[str]) -> None:
        self._responses = list(responses)
        self.requests: list[dict] = []

    def complete(self, *, system: str, messages: list[dict], model: str, max_tokens: int) -> LLMResponse:
        self.requests.append({"system": system, "messages": [dict(m) for m in messages], "model": model})
        if not self._responses:
            raise RuntimeError("ScriptedLLMClient ran out of scripted responses")
        text = self._responses.pop(0)
        prompt_chars = len(system) + sum(len(str(m.get("content", ""))) for m in messages)
        return LLMResponse(
            text=text, input_tokens=prompt_chars // 4, output_tokens=len(text) // 4, cost_usd=0.0, model=model
        )


class CachingLLMClient(LLMClient):
    """Disk cache in front of another client. Key = sha256 of (model, system, messages, max_tokens).

    A cache hit returns the ORIGINAL response's token counts and cost (flagged cached=True), so cost
    metrics stay reproducible across reruns instead of dropping to zero on the second run.
    """

    def __init__(self, inner: LLMClient, cache_dir: str | Path) -> None:
        self._inner = inner
        self._dir = Path(cache_dir)

    @staticmethod
    def key(*, system: str, messages: list[dict], model: str, max_tokens: int) -> str:
        payload = json.dumps(
            {"model": model, "system": system, "messages": messages, "max_tokens": max_tokens},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def complete(self, *, system: str, messages: list[dict], model: str, max_tokens: int) -> LLMResponse:
        path = (
            self._dir
            / f"{self.key(system=system, messages=messages, model=model, max_tokens=max_tokens)}.json"
        )
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return LLMResponse(**{**data, "cached": True})
        response = self._inner.complete(system=system, messages=messages, model=model, max_tokens=max_tokens)
        self._dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**asdict(response), "cached": False}), encoding="utf-8")
        return response


def build_llm_client(config: dict, *, cache: bool = True) -> LLMClient:
    """The configured real client, behind the disk cache unless disabled."""
    from sentinel.config import resolve_path

    client: LLMClient = AnthropicLLMClient(pricing=config.get("pricing_usd_per_mtok", {}))
    cache_dir = config.get("agent", {}).get("llm_cache_dir")
    if cache and cache_dir:
        client = CachingLLMClient(client, resolve_path(cache_dir))
    return client
