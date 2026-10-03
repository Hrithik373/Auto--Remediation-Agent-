#!/usr/bin/env python
"""`make demo-local` -- the live demo WITHOUT Docker: the gateway (uvicorn, offline_eval config) and the
console in live mode (`npm run dev:live`, proxying /api to the gateway). Ctrl-C stops both.

    console  http://localhost:5173     gateway  http://localhost:8080

Prometheus/Grafana need `make demo` (Docker); the gateway still serves /metrics here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODEL = REPO / "runs" / "models" / "learned_verifier.joblib"


def _wait_for(url: str, seconds: float = 30) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except OSError:
            time.sleep(0.5)
    return False


def main() -> None:
    if not MODEL.exists():
        print("no learned-verifier model yet -- training it (make train)")
        subprocess.run([sys.executable, str(REPO / "scripts" / "train_learned.py")], check=True)
    env = {**os.environ, "SENTINEL_CONFIG": "config/offline_eval.yaml", "PYTHONPATH": str(REPO / "src")}
    gateway = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sentinel.gateway.app:app", "--port", "8080"], cwd=REPO, env=env
    )
    if not _wait_for("http://127.0.0.1:8080/health"):
        gateway.terminate()
        sys.exit("gateway did not come up on :8080")
    console = subprocess.Popen("npm run dev:live", cwd=REPO / "frontend", shell=True)
    print("\n  console  http://localhost:5173   (live mode)")
    print("  gateway  http://localhost:8080\n  Ctrl-C to stop\n")
    try:
        console.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (console, gateway):
            proc.terminate()


if __name__ == "__main__":
    main()
