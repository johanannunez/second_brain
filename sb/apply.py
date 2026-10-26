"""Validate worker artifacts and produce a no-side-effect apply plan."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sb.actions import (
    ActionItem,
    TodoistComplete,
    parse_actions,
    validate_action_context,
    validate_file_changes,
)
from sb.redact import redact


@dataclass(frozen=True)
class ApplyPlan:
    worker: str
    actions: tuple[ActionItem, ...]
    writes: tuple[str, ...]


def validate_run(
    worker: str,
    actions_payload: object,
    changes: dict[str, str | None],
    *,
    source_data: dict[str, object] | None = None,
) -> ApplyPlan:
    """Validate the complete model output before any provider handler runs."""
    actions = parse_actions(actions_payload, worker)
    context_errors = validate_action_context(actions, source_data or {})
    if context_errors:
        raise ValueError("; ".join(context_errors))
    path_errors = validate_file_changes(worker, changes)
    if path_errors:
        raise ValueError("; ".join(path_errors))
    return ApplyPlan(worker=worker, actions=tuple(actions), writes=tuple(sorted(changes)))


def execute_actions(
    plan: ApplyPlan,
    handlers: dict[str, Any],
) -> list[dict[str, str]]:
    """Execute only injected handlers; outbox handlers create approval issues, never send."""
    results: list[dict[str, str]] = []
    for action in plan.actions:
        handler = handlers.get(action.type)
        if handler is None:
            raise ValueError(f"no apply handler configured for {action.type}")
        handler(action)
        result = {"type": action.type, "result": "completed"}
        if isinstance(action, TodoistComplete):
            result["proof"] = f"{action.proof_source}: {action.proof_detail}"
        results.append(result)
    return results


def write_worker_files(
    root: Path,
    worker: str,
    changes: dict[str, str | None],
) -> list[str]:
    """Write only allowlisted, nondeleted worker files, redacting before persistence."""
    errors = validate_file_changes(worker, changes)
    if errors:
        raise ValueError("; ".join(errors))
    repository = root.resolve(strict=True)
    targets: list[tuple[Path, str]] = []
    for raw_path, contents in changes.items():
        assert contents is not None
        relative = PurePosixPath(raw_path)
        current = repository
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"symlink paths are forbidden: {raw_path}")
        target = current.resolve(strict=False)
        if not target.is_relative_to(repository):
            raise ValueError(f"path escapes repository: {raw_path}")
        safe_text, _ = redact(contents)
        targets.append((target, safe_text))

    written: list[str] = []
    for target, contents in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not target.is_file():
            raise ValueError(
                f"worker output target is not a file: {target.relative_to(repository)}"
            )
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                delete=False,
            ) as stream:
                temp_path = Path(stream.name)
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_path, mode)
            os.replace(temp_path, target)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        written.append(target.relative_to(repository).as_posix())
    return written
