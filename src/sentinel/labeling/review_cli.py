# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Command-line tool for a human to accept or correct labels flagged needs_review.
# The only path that marks a label human_reviewed, with reviewer and timestamp.
"""Human-in-the-loop label review (blueprint §6.1): walk a fixture's `needs_review` labels and accept
or correct each one. The only code path that sets provenance = "human_reviewed".

    python -m sentinel.labeling.review_cli --status
    python -m sentinel.labeling.review_cli fixtures/incidents/itbench-sre-scenario-4.json --reviewer alice

A reviewed entry records who and when, and -- if the label changed -- the original label and
provenance, so the oracle-derived -> human-reviewed trail stays auditable. Rule-augmented hard cases
(labeling/augment.py) are not stored in fixtures; review those by reviewing config/labeling_rules.yaml.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "incidents"
_KEYS = {"a": None, "c": "correct", "i": "ineffective", "d": "destructive", "o": "out_of_envelope"}
PROMPT = "[a]ccept  relabel: [c]orrect [i]neffective [d]estructive [o]ut_of_envelope  [s]kip  [q]uit > "


def _summary(data: dict) -> list[str]:
    t = data["telemetry"]
    lines = [
        f"incident {data['incident_id']} ({data.get('source')}), fault_family={data.get('fault_family')}"
    ]
    lines += [
        f"  alert: {a.get('name')} on {a.get('target')} -- {a.get('description', '')[:90]}"
        for a in t["alerts"][:5]
    ]
    if data.get("itbench", {}).get("root_cause"):
        lines.append(f"  ITBench root cause: {data['itbench']['root_cause']}")
    return lines


def _apply(entry: dict, new_label: str | None, reviewer: str) -> None:
    if new_label and new_label != entry["label"]:
        entry["original_label"] = entry["label"]
        entry["label"] = new_label
    entry["original_provenance"] = entry.get("provenance", "hand_built")
    entry["provenance"] = "human_reviewed"
    entry["needs_review"] = False
    entry["reviewed_by"] = reviewer
    entry["reviewed_at"] = date.today().isoformat()


def review_fixture(
    path: Path, reviewer: str, *, ask: Callable[[str], str] = input, say: Callable[[str], None] = print
) -> Counter:
    """Interactively review one fixture's pending labels; writes the file after every decision."""
    data = json.loads(path.read_text(encoding="utf-8"))
    tally: Counter = Counter()
    for line in _summary(data):
        say(line)
    for entry in data["oracle"]["labeled_actions"]:
        if not entry.get("needs_review"):
            continue
        params = json.dumps(entry["params"])
        say(f"\n{entry['label'].upper():16} {entry['action_type']} -> {entry['target']} {params}")
        say(f"  note: {entry.get('note', '')}")
        if entry.get("review_note"):
            say(f"  review note: {entry['review_note']}")
        choice = ask(PROMPT).strip().lower()[:1]
        if choice == "q":
            break
        if choice not in _KEYS:
            tally["skipped"] += 1
            continue
        _apply(entry, _KEYS[choice], reviewer)
        tally["relabeled" if entry.get("original_label") else "accepted"] += 1
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return tally


def status(fixtures_dir: Path = FIXTURES_DIR) -> dict[str, Counter]:
    out: dict[str, Counter] = {}
    for path in sorted(fixtures_dir.glob("*.json")):
        entries = json.loads(path.read_text(encoding="utf-8"))["oracle"]["labeled_actions"]
        out[path.stem] = Counter(
            (
                "human_reviewed"
                if e.get("provenance") == "human_reviewed"
                else "needs_review" if e.get("needs_review") else "unreviewed_trusted"
            )
            for e in entries
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("fixture", nargs="?", type=Path)
    parser.add_argument("--reviewer", default="reviewer")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status or args.fixture is None:
        totals: Counter = Counter()
        for name, counts in status().items():
            totals.update(counts)
            print(f"{name:32} {dict(counts)}")
        print(f"\nTOTAL {dict(totals)}")
        return
    print(dict(review_fixture(args.fixture, args.reviewer)))


if __name__ == "__main__":
    main()
