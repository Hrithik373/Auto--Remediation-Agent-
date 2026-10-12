"""Phase P1: LLM client plumbing -- cost accounting, disk cache, config hashing, gateway endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sentinel.config import config_hash, load_config
from sentinel.gateway import app as gateway_app
from sentinel.gateway.clients import CachingLLMClient, LLMResponse, ScriptedLLMClient, UsageLedger, price_usd

PRICING = {"paid-model": {"input": 2.0, "output": 10.0}}


def test_price_usd_known_and_unknown_models():
    assert price_usd("paid-model", 1_000_000, 100_000, PRICING) == (3.0, True)
    assert price_usd("mystery-model", 10, 10, PRICING) == (0.0, False)


def test_ledger_accumulates_and_flags_unknown_cost():
    ledger = UsageLedger()
    ledger.record(LLMResponse("a", 100, 20, 0.5, model="m1"))
    ledger.record(LLMResponse("b", 10, 5, 0.0, model="m2", cost_known=False))
    assert ledger.calls == 2 and ledger.total_tokens == 135 and ledger.cost_usd == 0.5
    assert ledger.cost_known is False
    assert ledger.by_model["m1"]["tokens"] == 120


def test_cache_replays_identical_requests_with_original_cost(tmp_path):
    inner = ScriptedLLMClient(["first answer"])  # a second real call would raise: out of responses
    client = CachingLLMClient(inner, tmp_path)
    kwargs = {"system": "s", "messages": [{"role": "user", "content": "hi"}], "model": "m", "max_tokens": 10}
    first = client.complete(**kwargs)
    second = client.complete(**kwargs)
    assert first.cached is False and second.cached is True
    assert second.text == "first answer" and second.total_tokens == first.total_tokens
    assert len(inner.requests) == 1


def test_config_hash_is_stable_and_sensitive():
    base = load_config()
    assert config_hash(base) == config_hash(load_config())
    assert config_hash(base) != config_hash(load_config(overrides={"verifier": {"threshold": 0.7}}))
    assert base["execution"]["auto_execute"] is False  # golden rule: default config never auto-executes


def test_gateway_chat_and_usage(monkeypatch):
    monkeypatch.setitem(gateway_app._state, "client", ScriptedLLMClient(["pong"]))
    monkeypatch.setitem(gateway_app._state, "ledger", UsageLedger())
    client = TestClient(gateway_app.app)
    assert client.get("/health").json() == {"status": "ok"}
    reply = client.post("/chat", json={"messages": [{"role": "user", "content": "ping"}]}).json()
    assert reply["text"] == "pong"
    assert client.get("/usage").json()["calls"] == 1
    assert client.post("/chat", json={"messages": []}).status_code == 422
