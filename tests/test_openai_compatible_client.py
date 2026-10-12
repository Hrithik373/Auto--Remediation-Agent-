"""OpenAI-compatible client (Groq / Ollama / OpenRouter) against a local fake server -- no network."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sentinel.config import load_config
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.gateway.clients import (
    AnthropicLLMClient,
    OpenAICompatibleLLMClient,
    build_provider_client,
)
from sentinel.orchestrator.factory import build_judge
from sentinel.schemas.action import ProposedAction


@pytest.fixture
def fake_server():
    """Serves queued (status, body) replies and records each request's headers + JSON body."""
    state = {"replies": [], "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 -- http.server API
            length = int(self.headers["Content-Length"])
            state["requests"].append(
                {
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": json.loads(self.rfile.read(length)),
                }
            )
            status, body = state["replies"].pop(0)
            self.send_response(status)
            if status == 429:
                self.send_header("retry-after", "0")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_port}/v1"
    yield state
    server.shutdown()


def _ok(text: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }


def test_parses_text_usage_and_sends_system_message_and_key(fake_server):
    fake_server["replies"].append((200, _ok('{"decision":"allow"}')))
    client = OpenAICompatibleLLMClient(
        base_url=fake_server["url"], api_key="k-123", pricing={"m": {"input": 1.0, "output": 2.0}}
    )
    resp = client.complete(
        system="SYS", messages=[{"role": "user", "content": "hi"}], model="m", max_tokens=50
    )
    assert resp.text == '{"decision":"allow"}' and resp.input_tokens == 120 and resp.output_tokens == 30
    assert resp.cost_known and resp.cost_usd == pytest.approx((120 * 1 + 30 * 2) / 1e6)
    req = fake_server["requests"][0]
    assert req["path"] == "/v1/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer k-123"
    assert req["body"]["messages"][0] == {"role": "system", "content": "SYS"}
    assert req["body"]["model"] == "m" and req["body"]["max_tokens"] == 50


def test_rate_limit_is_retried_then_succeeds(fake_server):
    fake_server["replies"] += [(429, {"error": "slow down"}), (200, _ok("ok"))]
    client = OpenAICompatibleLLMClient(base_url=fake_server["url"], max_retries=2)
    assert client.complete(system="s", messages=[], model="m", max_tokens=5).text == "ok"
    assert len(fake_server["requests"]) == 2
    assert "Authorization" not in fake_server["requests"][0]["headers"]  # keyless (e.g. Ollama)


def test_non_retryable_error_raises_with_detail(fake_server):
    fake_server["replies"].append((404, {"error": {"message": "model_not_found"}}))
    client = OpenAICompatibleLLMClient(base_url=fake_server["url"])
    with pytest.raises(RuntimeError, match="HTTP 404.*model_not_found"):
        client.complete(system="s", messages=[], model="nope", max_tokens=5)


def test_provider_selection_from_config(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    config = load_config()
    groq = build_provider_client(config, "groq")
    assert isinstance(groq, OpenAICompatibleLLMClient) and groq._api_key == "from-env"
    assert isinstance(build_provider_client(config, None), AnthropicLLMClient)  # default stays anthropic
    with pytest.raises(ValueError, match="unknown LLM provider"):
        build_provider_client(config, "nobody")


def test_judge_fails_closed_when_provider_is_unreachable(fake_server):
    fake_server["replies"].append((500, {"error": "boom"}))
    config = load_config()
    judge = build_judge(config, llm=OpenAICompatibleLLMClient(base_url=fake_server["url"]))
    incident = OfflineEnvAdapter().get_incident("pod-crashloop")
    action = ProposedAction(
        action_type="restart_pod",
        target="payments-api",
        params={"namespace": "prod", "pod_name": "payments-api-7d9f-xk2z"},
        rationale="r",
        predicted_effect="e",
    )
    verdict = judge.verify(incident, action)
    assert verdict.decision == "block" and verdict.risk_score == 1.0
    assert "fail-closed" in verdict.reasons[0]
