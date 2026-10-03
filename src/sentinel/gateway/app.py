"""FastAPI LLM gateway (blueprint §3): /chat routes to gateway/clients.py with token/cost accounting,
/usage reports it, /health for liveness. Also mounts gateway/api.py's /api/* router -- the triage
console's read/control API (FRONTEND_BLUEPRINT.md §5).

The LLM client is built lazily on the first /chat call, so the gateway starts (and /health, /usage,
/api work) with no Anthropic credentials configured.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sentinel.config import load_config
from sentinel.gateway.api import router as api_router
from sentinel.gateway.clients import LLMClient, UsageLedger, build_llm_client

app = FastAPI(title="sentinel-remediate gateway")
app.include_router(api_router)

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
        _state["client"] = build_llm_client(load_config())
    return _state["client"]  # type: ignore[return-value]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    config = load_config()
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
