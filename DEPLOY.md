# Deploying the demo on Render (free tier)

One free Render **web service** runs the whole demo: the FastAPI gateway serves the API and the built
console from the same URL, so the live run stream (SSE) needs no proxy. Files:
[render.yaml](render.yaml) (Render Blueprint), [Dockerfile.render](Dockerfile.render) (image),
[config/render.yaml](config/render.yaml) (public-safe settings), [deploy/results_snapshot.json](deploy/results_snapshot.json)
(the Results screen's data).

## Steps

1. Push this repository to GitHub (Render deploys from a Git repo).
2. In the Render dashboard: **New → Blueprint**, connect GitHub, pick this repository. Render reads
   `render.yaml` and creates the `sentinel-remediate` web service on the **Free** plan.
3. Optional: in the service's **Environment** tab set `GROQ_API_KEY`. Without it everything still runs:
   the LLM judge fails closed (blocks) and the assistant answers in offline mode.
4. Wait for the first build (a few minutes: it builds the console, installs Python deps and trains the
   learned verifier), then open the service URL.

Every push to the deployed branch redeploys automatically (`autoDeploy: true`).

## What works, what doesn't

| Part | On the free service |
|---|---|
| Queue, Triage, live runs (SSE), VerdictCard | Yes |
| Learned / envelope / ungated variants | Yes, offline |
| LLM judge, Combined variant, Assistant LLM mode | Yes with `GROQ_API_KEY` (Groq free tier: 7000 input tokens/min, so expect pauses) |
| Assistant offline mode, scenario form | Yes |
| Results screen | Yes, from `deploy/results_snapshot.json` (a copy of `runs/eval/results.json` from `make eval`) |
| Observability (Prometheus + Grafana) | No: needs two more always-on services with storage. Raw counters stay at `/metrics`. |
| Real (non-dry-run) execution | Refused on purpose (`auto_execute: false`); runs are verified and planned only |

## Free-tier limits to know

- **Sleeps after 15 minutes without traffic**; the next visit takes about a minute to wake it.
- **512 MB RAM.** Measured with `docker run -m 512m`: about 150 MB in use after a run, a scenario and
  the assistant.
- **Ephemeral disk.** Console runs (DuckDB) and the LLM cache are lost on every restart or redeploy.
  The Results screen doesn't depend on them.
- **750 free instance hours per month** per workspace.

## Safety on a public URL

Anyone with the link can use the demo, so `config/render.yaml` keeps it dry-run only, turns off the raw
`/chat` LLM proxy (so your key can't be used as a free LLM relay), and keeps the key in Render's
environment, never in the repo. The judge and the assistant still spend your Groq quota when visitors
use them; leave `GROQ_API_KEY` unset for a fully offline demo.

## Updating the Results snapshot

After a new `make eval`: `cp runs/eval/results.json deploy/results_snapshot.json`, commit, push.

## Try the image locally

```bash
docker build -f Dockerfile.render -t sentinel-render .
docker run --rm -m 512m -e PORT=10000 -p 10000:10000 sentinel-render   # http://localhost:10000
```
