#!/usr/bin/env python
"""`make train` -- Phase P3 acceptance (ARCHITECTURE_BLUEPRINT.md §8): labeled dataset built and split
by incident; the XGBoost verifier reports AUC + ECE on held-out incidents.

Writes (all regenerable, under gitignored runs/):
  runs/models/learned_verifier.joblib              -- full feature set (used by variants learned/combined)
  runs/models/learned_verifier_no_topology.joblib  -- topology features dropped (P4 threat-to-validity
                                                      ablation: ITBench topology is curated around the fault)
  runs/models/learned_verifier_metrics.json        -- out-of-fold metrics for both
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentinel.config import load_config, resolve_path  # noqa: E402
from sentinel.env.offline_adapter import OfflineEnvAdapter  # noqa: E402
from sentinel.labeling.dataset import build_dataset, describe  # noqa: E402
from sentinel.verifier.learned import (  # noqa: E402
    classification_metrics,
    mixed_label_types,
    train_bundle,
    type_only_baseline,
)


def _subset_metrics(bundle: dict, baseline_p: list[float]) -> dict:
    oof = bundle["oof"]
    y, p = np.array(oof["y"]), np.array(oof["p"])
    source = np.array(["itbench" if i.startswith("itbench") else "p0" for i in oof["incident_id"]])
    scale = np.array([t == "scale_deployment" for t in oof["action_type"]])
    mixed = np.array([t in mixed_label_types(oof["action_type"], oof["y"]) for t in oof["action_type"]])
    return {
        # The honest headline: rows whose action type occurs with both labels, so type can't decide.
        "within_type_contrast": classification_metrics(y[mixed], p[mixed]),
        "within_type_contrast_type_only_baseline": classification_metrics(
            y[mixed], np.array(baseline_p)[mixed]
        ),
        "within_type_contrast_types": sorted(mixed_label_types(oof["action_type"], oof["y"])),
        "all": bundle["metrics"],
        "p0_incidents": classification_metrics(y[source == "p0"], p[source == "p0"]),
        "itbench_incidents": classification_metrics(y[source == "itbench"], p[source == "itbench"]),
        # The residue the envelope cannot catch: everything except scale_deployment (whose destructive
        # cases are scale-to-zero, blocked structurally by the envelope's replicas >= 1 floor).
        "excluding_scale_deployment": classification_metrics(y[~scale], p[~scale]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seed", type=int, default=None, help="default: config orchestrator.seed")
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args()

    config = load_config()
    seed = config["orchestrator"]["seed"] if args.seed is None else args.seed
    env = OfflineEnvAdapter()
    rows = build_dataset(env)
    incidents = {i: env.get_incident(i) for i in env.list_incidents()}
    print("dataset:", json.dumps(describe(rows)))

    out_path = resolve_path(config["verifier"]["learned_model_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    baseline = type_only_baseline(rows, args.folds)
    print(
        f"{'type-only baseline':32} out-of-fold AUC={baseline['auc']} ECE={baseline['ece']} "
        f"Brier={baseline['brier']}  <- the bar the learned verifier must clear"
    )
    baseline_p = baseline.pop("oof_p")
    report = {"dataset": describe(rows), "seed": seed, "folds": args.folds, "type_only_baseline": baseline}
    for name, use_topology in (("learned_verifier", True), ("learned_verifier_no_topology", False)):
        bundle = train_bundle(rows, incidents, seed=seed, n_folds=args.folds, use_topology=use_topology)
        path = out_path.with_name(f"{name}.joblib")
        joblib.dump(bundle, path)
        report[name] = _subset_metrics(bundle, baseline_p)
        m = bundle["metrics"]
        print(
            f"{name:32} out-of-fold AUC={m['auc']} ECE={m['ece']} Brier={m['brier']} "
            f"(n={m['n']}, destructive={m['positives']}) -> {path.name}"
        )
        mixed, base = (
            report[name]["within_type_contrast"],
            report[name]["within_type_contrast_type_only_baseline"],
        )
        print(
            f"{'':32}   within-type contrast ({', '.join(report[name]['within_type_contrast_types'])}; "
            f"n={mixed['n']}): AUC={mixed['auc']} vs type-only {base['auc']}; "
            f"Brier={mixed['brier']} vs {base['brier']}"
        )
    out_path.with_name("learned_verifier_metrics.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
