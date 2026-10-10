#!/usr/bin/env python
"""`make frontend-guide` -- builds docs/frontend_guide.pdf from docs/frontend_guide/{front,body}.html.

    python scripts/build_frontend_guide.py --capture   # refresh screenshots (needs `make demo-local` running)
    python scripts/build_frontend_guide.py             # render the PDF from the committed screenshots

Screenshots are taken from the running console in LIVE mode (gateway on :8080, console on :5173) and
saved to docs/frontend_guide/assets/, so the PDF can be rebuilt later without the services running.
Rendering reuses scripts/build_report.py's pipeline (headless Chromium + pypdf contents pages).
"""

from __future__ import annotations

import argparse
import html
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_report import entries, fill, git_commit, page_index, render, toc_html  # noqa: E402

SRC = REPO / "docs" / "frontend_guide"
ASSETS = SRC / "assets"
BUILD = SRC / "build"
OUT = REPO / "docs" / "frontend_guide.pdf"
CONSOLE = "http://localhost:5173"
SHOTS = {
    "shot_queue": "queue.png",
    "shot_triage": "triage.png",
    "shot_telemetry_metrics": "telemetry_metrics.png",
    "shot_run_controls": "run_controls.png",
    "shot_timeline_resolved": "timeline_resolved.png",
    "shot_verdict_blocked": "verdict_blocked.png",
    "shot_results": "results.png",
    "shot_observability": "observability.png",
}


# -- screenshot capture (live console) -------------------------------------------------------------


def _card(page, title: str):
    """The Card whose header reads `title` (Card renders titles as uppercase h3)."""
    return page.locator("div.rounded-lg").filter(has=page.locator("h3", has_text=title)).first


def _run(page, incident_id: str, verifier: str) -> None:
    page.goto(f"{CONSOLE}/incidents/{incident_id}")
    page.get_by_role("button", name=verifier, exact=True).click()
    dry_run = page.get_by_label("Dry-run (never reaches real apply)")
    if dry_run.is_checked():
        dry_run.uncheck()
    page.get_by_role("button", name="Start run").click()
    page.locator("dt", has_text="Unsafe action reached exec").wait_for(timeout=30_000)


def capture() -> None:
    from playwright.sync_api import sync_playwright

    ASSETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.goto(CONSOLE)
        page.get_by_text("live gateway").wait_for()
        page.get_by_text("itbench-sre-scenario-12").wait_for()
        page.screenshot(
            path=str(ASSETS / SHOTS["shot_queue"]), clip={"x": 0, "y": 0, "width": 1440, "height": 720}
        )

        page.goto(f"{CONSOLE}/incidents/pod-crashloop")
        page.get_by_role("button", name="Start run").wait_for()
        page.wait_for_timeout(800)  # let React Flow fit the topology
        page.screenshot(
            path=str(ASSETS / SHOTS["shot_triage"]), clip={"x": 0, "y": 0, "width": 1440, "height": 560}
        )
        page.get_by_role("button", name="Metrics", exact=True).click()
        page.locator("div.rounded-lg").filter(has=page.get_by_role("button", name="Logs")).first.screenshot(
            path=str(ASSETS / SHOTS["shot_telemetry_metrics"])
        )
        _card(page, "Run controls").screenshot(path=str(ASSETS / SHOTS["shot_run_controls"]))

        _run(page, "bad-rollout-latency", "Learned")
        _card(page, "Loop trace").screenshot(path=str(ASSETS / SHOTS["shot_timeline_resolved"]))

        _run(page, "itbench-sre-scenario-12", "Learned")
        _card(page, "Verdict").screenshot(path=str(ASSETS / SHOTS["shot_verdict_blocked"]))

        page.goto(f"{CONSOLE}/results")
        page.locator(".recharts-bar .recharts-rectangle").first.wait_for()
        page.screenshot(path=str(ASSETS / SHOTS["shot_results"]), full_page=True)
        page.goto(f"{CONSOLE}/observability")
        page.get_by_text("Observability").first.wait_for()
        page.screenshot(
            path=str(ASSETS / SHOTS["shot_observability"]),
            clip={"x": 0, "y": 0, "width": 1440, "height": 520},
        )
        browser.close()
    print(f"captured {len(SHOTS)} screenshots into {ASSETS.relative_to(REPO)}")


# -- build ----------------------------------------------------------------------------------------


def _count_lines(patterns: tuple[str, ...]) -> int:
    root = REPO / "frontend" / "src"
    return sum(
        len(f.read_text(encoding="utf-8").splitlines())
        for pat in patterns
        for f in root.rglob(pat)
        if f.name not in ("types.ts", "vite-env.d.ts")
    )


def values() -> dict[str, str]:
    missing = [name for name in SHOTS.values() if not (ASSETS / name).exists()]
    if missing:
        sys.exit(f"missing screenshots {missing} -- run with --capture while `make demo-local` is running")
    v = {key: (ASSETS / name).as_uri() for key, name in SHOTS.items()}
    v.update(
        {
            "title": "sentinel-console: A Guide to the Frontend",
            "document": "Frontend Guide",
            "date": date.today().strftime("%d %B %Y"),
            "commit": git_commit(),
            "loc_frontend": f"{_count_lines(('*.ts', '*.tsx')):,}",
            "n_components": str(len(list((REPO / "frontend" / "src" / "features").rglob("*.tsx")))),
        }
    )
    return v


def build() -> None:
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader, PdfWriter

    v = values()
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "report.css").write_text(
        (REPO / "docs" / "report" / "report.css").read_text(encoding="utf-8"), encoding="utf-8"
    )
    body = fill((SRC / "body.html").read_text(encoding="utf-8"), v)
    (BUILD / "body.html").write_text(body, encoding="utf-8")
    items = entries(body)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        render(page, BUILD / "body.html", BUILD / "body.pdf", numbered=True, title=v["document"])
        where = page_index(BUILD / "body.pdf", items)
        missing = [f"{lv} {num}" for lv, num, _ in items if f"{lv}:{num}" not in where]
        if missing:
            print("warning: page not found for", missing)
        v["toc"], v["lof"], v["lot"] = toc_html(items, where)
        (BUILD / "front.html").write_text(
            fill((SRC / "front.html").read_text(encoding="utf-8"), v), encoding="utf-8"
        )
        render(page, BUILD / "front.html", BUILD / "front.pdf", numbered=False, title=v["document"])
        browser.close()
    writer = PdfWriter()
    for part in ("front.pdf", "body.pdf"):
        for pg in PdfReader(str(BUILD / part)).pages:
            writer.add_page(pg)
    writer.add_metadata({"/Title": html.unescape(v["title"]), "/Subject": "Frontend guide"})
    with OUT.open("wb") as f:
        writer.write(f)
    n_front, n_body = len(PdfReader(str(BUILD / "front.pdf")).pages), len(
        PdfReader(str(BUILD / "body.pdf")).pages
    )
    print(
        f"wrote {OUT.relative_to(REPO)}: {n_front} front + {n_body} body pages, "
        f"{len(where)}/{len(items)} contents entries located"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--capture", action="store_true", help="refresh screenshots from the running console")
    parser.add_argument("--capture-only", action="store_true", help="refresh screenshots, skip the PDF")
    args = parser.parse_args()
    if args.capture or args.capture_only:
        capture()
    if not args.capture_only:
        build()


if __name__ == "__main__":
    main()
