# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Gateway package: the FastAPI backend the console talks to, plus the LLM clients.
# app.py is the server, api.py the /api routes, runs.py live runs, clients.py LLM access.
"""FastAPI LLM proxy: routing, token/cost accounting, request logs. Phase P1 (stub client) / P5
(full gateway) — see PROGRESS.md.
"""
