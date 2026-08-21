"""FastAPI LLM gateway — Phase P5. Not implemented yet; see PROGRESS.md.

Intended endpoints (blueprint §3, §8): /chat (routes to gateway/clients.py, records token/cost
accounting), /health. Fronted by docker-compose.yml's `gateway` service.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="sentinel-remediate gateway")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat() -> dict[str, str]:
    raise NotImplementedError("gateway.app /chat is Phase P5 work. See ARCHITECTURE_BLUEPRINT.md §3, §8.")
