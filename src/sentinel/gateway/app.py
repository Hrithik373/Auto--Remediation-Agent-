# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# The FastAPI app (uvicorn entry point): mounts /api, /metrics, and serves /health,
# /chat (LLM proxy with token/cost accounting) and /usage.
"""FastAPI LLM gateway (blueprint §3): /chat routes to gateway/clients.py with token/cost accounting,
/usage reports it, /health for liveness. Also mounts gateway/api.py's /api/* router -- the triage
console's read/control API (FRONTEND_BLUEPRINT.md §5).

The LLM client is built lazily on the first /chat call, so the gateway starts (and /health, /usage,
/api work) with no Anthropic credentials configured.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field

from sentinel.gateway.api import router as api_router
from sentinel.gateway.api import state as api_state
from sentinel.gateway.assistant_api import router as assistant_router
from sentinel.gateway.clients import LLMClient, UsageLedger, build_llm_client
from sentinel.observability.metrics import init_metrics

app = FastAPI(title="sentinel-remediate gateway")
app.include_router(api_router)
app.include_router(assistant_router)  # Phase P6: /api/assistant/* (ASSISTANT_BLUEPRINT.md)
# Prometheus scrape target (docker-compose.yml `prometheus` service -> config/prometheus.yml).
app.mount("/metrics", make_asgi_app(registry=init_metrics().registry))

_state: dict[str, object] = {"ledger": UsageLedger(), "client": None}


class ChatRequest(BaseModel):
    system: str = ""
    messages: list[dict] = Field(min_length=1)
    model: str | None = None
    max_tokens: int | None = Field(default=None, gt=0)


class ChatResponse(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cost_known: bool
    cached: bool


def _client() -> LLMClient:
    if _state["client"] is None:
        config = api_state()["config"]  # same provider as the default model /chat sends
        _state["client"] = build_llm_client(config, provider=config["models"].get("diagnosis_agent_provider"))
    return _state["client"]  # type: ignore[return-value]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    config = api_state()["config"]  # honours the $SENTINEL_CONFIG overlay, like /api
    if not config.get("gateway", {}).get("chat_proxy", True):
        # Public deployments switch the raw LLM proxy off so the API key can't be used as a free relay.
        raise HTTPException(status_code=404, detail="the /chat LLM proxy is disabled on this deployment")
    model = request.model or config["models"]["diagnosis_agent"]
    max_tokens = request.max_tokens or config["models"].get("max_tokens_per_call", 4096)
    try:
        response = _client().complete(
            system=request.system, messages=request.messages, model=model, max_tokens=max_tokens
        )
    except Exception as exc:  # surface provider/credential errors as a gateway error, not a 500 trace
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc
    _state["ledger"].record(response)  # type: ignore[union-attr]
    return ChatResponse(
        text=response.text,
        model=model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        cost_known=response.cost_known,
        cached=response.cached,
    )


@app.get("/usage")
def usage() -> dict:
    return _state["ledger"].snapshot()  # type: ignore[union-attr]


def mount_console(application: FastAPI, static_dir: str | None) -> bool:
    """Serve the built console (frontend/dist) from this same origin, for single-container deploys
    (Dockerfile.render). Unknown paths fall back to index.html so client routes like /assistant load.
    Registered LAST, so /api, /health, /chat, /usage and /metrics always win."""
    if not static_dir or not (Path(static_dir) / "index.html").is_file():
        return False
    root = Path(static_dir).resolve()
    if (root / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=root / "assets"), name="console-assets")

    @application.get("/{path:path}", include_in_schema=False)
    def console(path: str) -> FileResponse:
        if path.startswith(("api/", "metrics")):
            raise HTTPException(status_code=404, detail=f"no route /{path}")
        file = (root / path).resolve()
        if path and file.is_file() and root in file.parents:
            return FileResponse(file)
        return FileResponse(root / "index.html")

    return True


mount_console(app, os.environ.get("SENTINEL_STATIC_DIR"))
