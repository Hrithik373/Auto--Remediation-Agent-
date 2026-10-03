#!/usr/bin/env python
"""`make e2e` -- rehearses the live demo (FRONTEND_BLUEPRINT.md §9) in a headless browser against the
REAL gateway and the console in live mode (no MSW), and fails loudly if any step breaks.

  1. Queue lists every fixture incident.
  2. Happy path: bad-rollout-latency, Learned, tau 0.5, real apply -> the run streams and resolves.
  3. The thesis: itbench-sre-scenario-12 -- the agent proposes cordon_node; the envelope PASSES it and
     the learned layer BLOCKS it ("never reached executor"). Then the same incident Ungated: it executes.
  4. Results renders from the gateway's DuckDB rows.
Screenshots land in runs/e2e/. Needs `pip install playwright && python -m playwright install chromium`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "runs" / "e2e"
CONSOLE = "http://localhost:5173"


def _wait_for(url: str, seconds: float = 60) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up")


def _start_run(page, incident_id: str, verifier: str) -> None:
    page.goto(f"{CONSOLE}/incidents/{incident_id}")
    page.get_by_role("button", name=verifier, exact=True).click()
    dry_run = page.get_by_label("Dry-run (never reaches real apply)")
    if dry_run.is_checked():
        dry_run.uncheck()
    page.get_by_role("button", name="Start run").click()


def _unsafe_reached_exec(page) -> str:
    """Wait for the run summary (the stream's `final` event) and read its safety headline."""
    dt = page.locator("dt", has_text="Unsafe action reached exec")
    dt.wait_for(timeout=30_000)
    return dt.locator("xpath=following-sibling::dd").inner_text().strip()


def run_demo(page, errors: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.goto(CONSOLE)
    page.get_by_text("live gateway").wait_for()
    page.get_by_text("itbench-sre-scenario-12").wait_for()
    page.screenshot(path=str(OUT / "1_queue.png"), full_page=True)

    _start_run(page, "bad-rollout-latency", "Learned")
    assert _unsafe_reached_exec(page) == "no"
    page.get_by_text("applied · resolved", exact=True).first.wait_for()
    page.get_by_text("Resolved", exact=True).wait_for()
    page.screenshot(path=str(OUT / "2_happy_path.png"), full_page=True)

    # The thesis: cordon_node passes the envelope (allow-listed, valid params); the learned layer blocks it.
    _start_run(page, "itbench-sre-scenario-12", "Learned")
    assert _unsafe_reached_exec(page) == "no"
    page.get_by_text("blocked", exact=True).first.wait_for()
    page.get_by_text("cordon_node").first.wait_for()
    page.screenshot(path=str(OUT / "3_thesis_blocked.png"), full_page=True)

    # Same incident, no verifier: the destructive action executes.
    _start_run(page, "itbench-sre-scenario-12", "Ungated")
    assert _unsafe_reached_exec(page) == "yes", "ungated run should execute the destructive cordon_node"
    page.screenshot(path=str(OUT / "4_ungated_executes.png"), full_page=True)

    page.goto(f"{CONSOLE}/results")
    page.get_by_text("Risk–autonomy Pareto").wait_for()
    page.get_by_text("Bad-action prevention, by layer").wait_for()
    bars = page.locator(".recharts-bar .recharts-rectangle")  # bars actually drawn, not just axes
    bars.first.wait_for()
    assert bars.count() >= 3, "prevention partition rendered no bars"
    page.screenshot(path=str(OUT / "5_results.png"), full_page=True)
    if errors:
        raise AssertionError("browser console errors:\n" + "\n".join(errors))


def main() -> None:
    from playwright.sync_api import sync_playwright

    env = {**os.environ, "SENTINEL_CONFIG": "config/offline_eval.yaml", "PYTHONPATH": str(REPO / "src")}
    gateway = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sentinel.gateway.app:app", "--port", "8080"],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    console = subprocess.Popen(
        "npm run dev:live -- --port 5173 --strictPort",
        cwd=REPO / "frontend",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for("http://127.0.0.1:8080/health")
        _wait_for(CONSOLE)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            try:
                run_demo(page, errors)
            except Exception:
                page.screenshot(path=str(OUT / "FAILED.png"), full_page=True)
                print(f"rehearsal FAILED -- see {OUT.relative_to(REPO) / 'FAILED.png'}; errors: {errors}")
                raise
            browser.close()
        print(f"demo rehearsal PASSED -- screenshots in {OUT.relative_to(REPO)}")
    finally:
        gateway.terminate()
        if os.name == "nt":  # npm under a shell: kill the whole tree
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(console.pid)], capture_output=True)
        else:
            console.terminate()


if __name__ == "__main__":
    main()
