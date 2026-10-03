"""Phase P5c/d: the console API against a real orchestrator, isolated store and config overlay."""

from __future__ import annotations

import json

import joblib
import pytest
import yaml
from fastapi.testclient import TestClient

from sentinel.config import REPO_ROOT, load_config
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.eval.runner import Cell, run_grid
from sentinel.gateway import api
from sentinel.gateway.app import app
from sentinel.labeling.dataset import build_dataset
from sentinel.store.duckdb_store import DuckDBStore
from sentinel.verifier.learned import LearnedVerifier, train_bundle


@pytest.fixture(scope="module")
def model_path(tmp_path_factory):
    env = OfflineEnvAdapter()
    bundle = train_bundle(
        build_dataset(env), {i: env.get_incident(i) for i in env.list_incidents()}, n_folds=3
    )
    path = tmp_path_factory.mktemp("models") / "learned_verifier.joblib"
    joblib.dump(bundle, path)
    return path


def _client(monkeypatch, tmp_path, *, auto_execute: bool, model_path=None) -> TestClient:
    overlay = {
        "store": {"path": str(tmp_path / "gw.duckdb")},
        "gateway": {"step_delay_ms": 0},
        "execution": {"auto_execute": auto_execute, "dry_run": not auto_execute},
        "verifier": {"learned_model_path": str(model_path or tmp_path / "missing.joblib")},
        "eval": {"experiment": "t"},
    }
    path = tmp_path / "overlay.yaml"
    path.write_text(yaml.safe_dump(overlay), encoding="utf-8")
    monkeypatch.setenv("SENTINEL_CONFIG", str(path))
    api.reset_state_for_tests()
    return TestClient(app)


def _stream(client: TestClient, run_id: str) -> list[tuple[str, dict]]:
    events, kind = [], None
    with client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("event: "):
                kind = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((kind, json.loads(line.removeprefix("data: "))))
                if kind in ("final", "error"):
                    break
    return events


def test_incidents_and_config(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, auto_execute=False)
    incidents = client.get("/api/incidents").json()
    assert len(incidents) == len(OfflineEnvAdapter().list_incidents())
    assert all(i["status"] == "queued" for i in incidents)
    assert client.get("/api/incidents/pod-crashloop").json()["incident_id"] == "pod-crashloop"
    assert client.get("/api/incidents/nope").status_code == 404
    assert client.get("/api/config").json()["auto_execute"] is False


def test_live_run_streams_steps_then_final_and_is_stored(monkeypatch, tmp_path, model_path):
    client = _client(monkeypatch, tmp_path, auto_execute=True, model_path=model_path)
    run_id = client.post(
        "/api/runs",
        json={"incident_id": "bad-rollout-latency", "verifier": "learned", "tau": 0.5, "dry_run": False},
    ).json()["run_id"]
    events = _stream(client, run_id)
    kinds = [k for k, _ in events]
    assert kinds[-1] == "final" and set(kinds[:-1]) == {"step"} and len(kinds) >= 2
    final = events[-1][1]
    assert len(final["steps"]) == len(kinds) - 1
    assert all(len(step["verdict"]["layers"]) == 3 for _, step in events[:-1])  # layered VerdictCard data
    assert client.get(f"/api/runs/{run_id}").json() == final
    assert client.get("/api/runs").json()[0] == final
    assert _stream(client, run_id)[-1][0] == "final"  # reconnect replays the whole log
    status = {i["incident_id"]: i["status"] for i in client.get("/api/incidents").json()}
    assert status["bad-rollout-latency"] != "queued"
    step = client.post(f"/api/runs/{run_id}/decision", json={"step_idx": 0, "human_decision": "reject"})
    assert step.status_code == 200 and step.json() == final["steps"][0]


def test_real_execution_refused_without_auto_execute(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, auto_execute=False)
    response = client.post(
        "/api/runs", json={"incident_id": "pod-crashloop", "verifier": "envelope", "dry_run": False}
    )
    assert response.status_code == 403 and "auto_execute" in response.json()["detail"]
    assert (
        client.post(
            "/api/runs", json={"incident_id": "pod-crashloop", "verifier": "envelope", "dry_run": True}
        ).status_code
        == 200
    )


def test_learned_variant_without_a_model_is_a_clear_409(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, auto_execute=False)
    response = client.post("/api/runs", json={"incident_id": "pod-crashloop", "verifier": "learned"})
    assert response.status_code == 409 and "make train" in response.json()["detail"]


def test_experiment_endpoints_read_eval_rows(monkeypatch, tmp_path, model_path):
    client = _client(monkeypatch, tmp_path, auto_execute=True, model_path=model_path)
    store = DuckDBStore(tmp_path / "gw.duckdb")
    config = load_config(REPO_ROOT / "config" / "offline_eval.yaml")
    learned = LearnedVerifier(model_path=model_path)
    # A destructive-heavy planner so the 2-incident grid is guaranteed destructive proposals to partition.
    heavy = {"agent": {"simulated": {"label_mix": {"correct": 0.2, "destructive": 0.8}}}}
    cells = [
        Cell("baselines", "envelope", 0.5, config_overrides=heavy),
        Cell("baselines", "learned", 0.5, learned=learned, config_overrides=heavy),
        Cell("pareto", "learned", 0.5, learned=learned),
    ]
    run_grid(
        OfflineEnvAdapter(),
        ["bad-rollout-latency", "pod-crashloop"],
        [0],
        config,
        cells=cells,
        experiment="t",
        store=store,
    )
    assert [m["variant"] for m in client.get("/api/experiments/metrics").json()] == ["envelope", "learned"]
    assert set(client.get("/api/experiments/pareto").json()) == {"learned"}
    rows = client.get("/api/experiments/prevention_partition").json()
    assert set(rows[0]) >= {"baseline", "caught_by_envelope", "caught_by_secondary_only", "missed"}
    assert isinstance(client.get("/api/experiments/ablations").json(), list)


def test_prometheus_metrics_exposed(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, auto_execute=False)
    run_id = client.post("/api/runs", json={"incident_id": "pod-crashloop", "verifier": "envelope"}).json()[
        "run_id"
    ]
    _stream(client, run_id)
    body = client.get("/metrics/").text
    assert "sentinel_verdicts_total" in body and "sentinel_step_latency_seconds" in body
