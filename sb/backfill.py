"""Build an evidence-only backfill proposal from normalized source facts.

The planner does not edit repository files or create a pull request. Provider
collection and the final review remain separate, explicit steps.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from sb.redact import redact

ROOT = Path(__file__).resolve().parents[1]
TARGET_ROOTS = ("profile.md", "businesses/", "people/", "properties/", "goals/")
SOURCE_TAG = re.compile(r"^[a-z][a-z0-9_-]*(?::[a-z0-9_-]+)?$")
SOURCE_DATE = re.compile(r"^\d{4}-(?:\d{2}|\d{2}-\d{2})$")
OPEN_MARKER = re.compile(r"\bTO (?:FILL|CONFIRM)\b")


def _target_allowed(target: str) -> bool:
    path = Path(target)
    normalized = path.as_posix()
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and any(normalized == prefix or normalized.startswith(prefix) for prefix in TARGET_ROOTS)
    )


def remaining_questions(root: Path = ROOT) -> list[dict[str, Any]]:
    """Report unresolved markers in files the backfill is allowed to update."""
    paths: list[Path] = []
    for target in TARGET_ROOTS:
        candidate = root / target
        if candidate.is_file():
            paths.append(candidate)
        elif candidate.is_dir():
            paths.extend(sorted(candidate.rglob("*.md")))
    questions: list[dict[str, Any]] = []
    for path in paths:
        if path.is_symlink():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if OPEN_MARKER.search(line):
                questions.append(
                    {
                        "file": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "question": line.strip(),
                    }
                )
    return questions


def plan_backfill(payload: object, *, root: Path = ROOT) -> dict[str, Any]:
    """Validate facts and return citations without touching repository files."""
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), list):
        raise ValueError("input must be an object containing a facts list")

    proposals: list[dict[str, str]] = []
    deferred: list[dict[str, str]] = []
    for index, item in enumerate(payload["facts"]):
        if not isinstance(item, dict):
            deferred.append({"item": str(index), "reason": "fact must be an object"})
            continue
        source = item.get("source")
        source_date = item.get("date")
        target = item.get("target")
        fact = item.get("fact")
        kind = item.get("kind", "context")

        # Todoist owns tasks. Do not file task records from Todoist or Notion into
        # profile/business memory, and never create task copies in Notion.
        if kind == "task" or (source == "notion" and kind in {"todo", "task"}):
            deferred.append({"item": str(index), "reason": "task records stay in Todoist"})
            continue
        if not isinstance(source, str) or not SOURCE_TAG.fullmatch(source):
            deferred.append({"item": str(index), "reason": "missing or invalid source tag"})
            continue
        if not isinstance(source_date, str) or not SOURCE_DATE.fullmatch(source_date):
            deferred.append({"item": str(index), "reason": "missing or invalid source date"})
            continue
        if not isinstance(target, str) or not _target_allowed(target):
            deferred.append(
                {"item": str(index), "reason": "target path is outside backfill allowlist"}
            )
            continue
        if not isinstance(fact, str) or not fact.strip():
            deferred.append({"item": str(index), "reason": "fact text is empty"})
            continue

        safe_fact, flags = redact(fact.strip())
        if flags or safe_fact != fact.strip():
            deferred.append({"item": str(index), "reason": "privacy redaction required"})
            continue
        proposals.append(
            {
                "target": target,
                "fact": safe_fact,
                "citation": f"[{source}, {source_date}]",
            }
        )

    return {
        "mode": "proposal only; repository unchanged",
        "proposals": proposals,
        "deferred": deferred,
        "remaining_questions": remaining_questions(root),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    print(json.dumps(plan_backfill(payload), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
