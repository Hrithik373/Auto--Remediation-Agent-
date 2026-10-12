import { http, HttpResponse, delay } from "msw";
import type { RunRecord, StepRecord } from "@/api/types";
import {
  ABLATION_ROWS,
  CANNED_RUNS,
  INCIDENT_CONTEXTS,
  INCIDENT_SUMMARIES,
  METRICS_ROWS,
  PARETO_SERIES,
  PREVENTION_PARTITION,
} from "./fixtures";

/**
 * MSW handlers implementing the API contract in FRONTEND_BLUEPRINT.md §5.1. The whole console must
 * render from these with zero backend (CLAUDE.md frontend addendum) -- including a *simulated* live
 * loop: POST /api/runs seeds an in-memory run from a canned RunRecord's steps, and the SSE handler
 * replays them with real delays so LoopTimeline genuinely streams rather than appearing pre-formed.
 * This is honestly a demo trick, not a real orchestrator -- src/sentinel/orchestrator/loop.py (Phase
 * P2) is what actually produces these steps once the backend exists; see gateway/api.ts's docstring.
 */

let runCounter = 0;
const pendingRuns = new Map<string, { incidentId: string; steps: StepRecord[]; final: RunRecord }>();
const finishedRuns = new Map<string, RunRecord>();

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

export const handlers = [
  http.get("/api/incidents", async () => {
    await delay(180);
    return HttpResponse.json(INCIDENT_SUMMARIES);
  }),

  http.get("/api/incidents/:id", async ({ params }) => {
    await delay(140);
    const incident = INCIDENT_CONTEXTS[params.id as string];
    if (!incident) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(incident);
  }),

  http.get("/api/config", async () => {
    return HttpResponse.json({
      models: { diagnosis_agent: "qwen/qwen3.8-27b", llm_judge: "qwen/qwen3.8-27b" },
      verifier_choice: "combined",
      tau: 0.5,
      auto_execute: false,
      max_steps: 6,
    });
  }),

  http.post("/api/runs", async ({ request }) => {
    const body = (await request.json()) as { incident_id: string };
    const canned = CANNED_RUNS[body.incident_id];
    const runId = `mock-run-${++runCounter}`;
    if (canned) {
      pendingRuns.set(runId, { incidentId: body.incident_id, steps: canned.steps ?? [], final: canned });
    } else {
      // No canned run for this incident yet -- stream a single "escalated, needs a real agent" step.
      pendingRuns.set(runId, {
        incidentId: body.incident_id,
        steps: [],
        final: {
          incident_id: body.incident_id,
          seed: 0,
          config_hash: "mock-none",
          steps: [],
          final_resolved: false,
          unsafe_action_reached_exec: false,
          mttm_ms: null,
          total_tokens: 0,
          total_cost_usd: 0,
        },
      });
    }
    await delay(120);
    return HttpResponse.json({ run_id: runId });
  }),

  http.get("/api/runs/:runId/stream", ({ params }) => {
    const runId = params.runId as string;
    const pending = pendingRuns.get(runId);

    const stream = new ReadableStream({
      async start(controller) {
        const encoder = new TextEncoder();
        if (!pending) {
          controller.close();
          return;
        }
        for (const step of pending.steps) {
          await new Promise((r) => setTimeout(r, 900));
          controller.enqueue(encoder.encode(sse("step", step)));
        }
        await new Promise((r) => setTimeout(r, 500));
        finishedRuns.set(runId, pending.final);
        controller.enqueue(encoder.encode(sse("final", pending.final)));
        controller.close();
      },
    });

    return new HttpResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }),

  http.get("/api/runs", async () => {
    await delay(150);
    return HttpResponse.json([...finishedRuns.values(), ...Object.values(CANNED_RUNS)]);
  }),

  http.get("/api/runs/:runId", async ({ params }) => {
    await delay(120);
    const runId = params.runId as string;
    const run = finishedRuns.get(runId) ?? pendingRuns.get(runId)?.final;
    if (!run) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(run);
  }),

  http.post("/api/runs/:runId/decision", async ({ request }) => {
    const body = await request.json();
    await delay(150);
    return HttpResponse.json(body);
  }),

  http.get("/api/experiments/pareto", async ({ request }) => {
    await delay(160);
    const url = new URL(request.url);
    const verifierParam = url.searchParams.get("verifier");
    if (verifierParam && PARETO_SERIES[verifierParam]) {
      return HttpResponse.json({ [verifierParam]: PARETO_SERIES[verifierParam] });
    }
    return HttpResponse.json(PARETO_SERIES);
  }),

  http.get("/api/experiments/metrics", async () => {
    await delay(160);
    return HttpResponse.json(METRICS_ROWS);
  }),

  http.get("/api/experiments/prevention_partition", async () => {
    await delay(160);
    return HttpResponse.json(PREVENTION_PARTITION);
  }),

  http.get("/api/experiments/ablations", async () => {
    await delay(160);
    return HttpResponse.json(ABLATION_ROWS);
  }),
];
