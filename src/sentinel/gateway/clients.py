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


class OpenAICompatibleLLMClient(LLMClient):
    """Any OpenAI-style /chat/completions endpoint: Groq (free tier), Ollama (local), OpenRouter, vLLM.

    stdlib only (urllib), so it adds no dependency. Rate limits (HTTP 429) are retried after the
    server's retry-after, up to `max_retries`; anything else raises, and the LLM judge turns that into
    a fail-closed BLOCK.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        pricing: dict | None = None,
        timeout_s: float = 60,
        max_retries: int = 3,
        max_wait_s: float = 30,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._pricing = pricing or {}
        self._timeout = timeout_s
        self._max_retries = max_retries
        self._max_wait = max_wait_s

    def _post(self, body: dict) -> dict:
        import time
        import urllib.error
        import urllib.request

        headers = {"Content-Type": "application/json", "User-Agent": "sentinel-remediate/1.0"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        data = json.dumps(body).encode("utf-8")
        for attempt in range(self._max_retries + 1):
            request = urllib.request.Request(self._url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                if exc.code != 429 or attempt == self._max_retries:
                    raise RuntimeError(f"HTTP {exc.code} from {self._url}: {detail}") from exc
                wait = _retry_after_s(exc.headers.get("retry-after"), default=2.0 * (attempt + 1))
                time.sleep(min(wait, self._max_wait))
        raise AssertionError("unreachable")

    def complete(self, *, system: str, messages: list[dict], model: str, max_tokens: int) -> LLMResponse:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        data = self._post(body)
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        input_tokens, output_tokens = int(usage.get("prompt_tokens", 0)), int(
            usage.get("completion_tokens", 0)
        )
        cost, known = price_usd(model, input_tokens, output_tokens, self._pricing)
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model=model,
            cost_known=known,
        )


def _retry_after_s(header: str | None, *, default: float) -> float:
    try:
        return max(0.0, float(header)) if header else default
    except ValueError:
        return default


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


def build_provider_client(config: dict, provider: str | None) -> LLMClient:
    """The raw client for a named provider in config `llm_providers` (default: anthropic)."""
    import os

    pricing = config.get("pricing_usd_per_mtok", {})
    name = provider or "anthropic"
    spec = config.get("llm_providers", {}).get(name, {"kind": "anthropic"} if name == "anthropic" else None)
    if spec is None:
        raise ValueError(f"unknown LLM provider {name!r}; define it under llm_providers in the config")
    if spec["kind"] == "anthropic":
        return AnthropicLLMClient(pricing=pricing)
    if spec["kind"] == "openai_compatible":
        key_env = spec.get("api_key_env")
        return OpenAICompatibleLLMClient(
            base_url=spec["base_url"], api_key=os.environ.get(key_env) if key_env else None, pricing=pricing
        )
    raise ValueError(f"LLM provider {name!r} has unknown kind {spec['kind']!r}")


def build_llm_client(config: dict, *, provider: str | None = None, cache: bool = True) -> LLMClient:
    """The configured real client for `provider`, behind the disk cache unless disabled."""
    from sentinel.config import resolve_path

    client: LLMClient = build_provider_client(config, provider)
    cache_dir = config.get("agent", {}).get("llm_cache_dir")
    if cache and cache_dir:
        client = CachingLLMClient(client, resolve_path(cache_dir))
    return client
