"""Preview fixture-driven worker outputs without provider writes or file changes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sb.apply import validate_run
from sb.collect import collect_run

ROOT = Path(__file__).resolve().parents[1]
WORKERS = ("morning-briefing", "midday-sweep", "evening-check-in", "weekly-review", "monthly-close")


class FixtureCollector:
    def __init__(self, name: str, payload: object) -> None:
        self.name = name
        self.payload = payload

    def collect(self) -> object:
        return self.payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=WORKERS, required=True)
    args = parser.parse_args()
    fixture_path = ROOT / "tests" / "fixtures" / "dry-run" / f"{args.worker}.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    collected = collect_run([FixtureCollector("fixture", fixture["source_data"])])
    actions_payload = fixture["actions"]
    changes = fixture["changes"]
    plan = validate_run(args.worker, actions_payload, changes)
    output = {
        "worker": plan.worker,
        "fixture": fixture_path.name,
        "source_keys": sorted(collected["sources"]["fixture"]),
        "redaction_flags": collected["redaction_flags"],
        "would_write": list(plan.writes),
        "would_apply": [action.model_dump(mode="json") for action in plan.actions],
        "mode": "dry-run, no files or provider calls executed",
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
