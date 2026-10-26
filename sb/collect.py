"""Collect independent source payloads, redact them, and attach run metadata."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sb.redact import redact
from sb.timegate import run_metadata


class Collector(Protocol):
    name: str

    def collect(self) -> Any: ...


class CollectorError(Exception):
    """A safe, summary-ready source error without response bodies or credentials."""

    def __init__(self, source: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.source = source
        self.message = message
        self.status_code = status_code

    def summary(self) -> str:
        suffix = f" (HTTP {self.status_code})" if self.status_code else ""
        safe_message, flags = redact(self.message)
        message = "provider error details redacted" if flags else str(safe_message)
        message = message.replace("\n", " ").replace("\r", " ")
        return f"{message[:160]}{suffix}"


def collect_run(
    collectors: Iterable[Collector],
    *,
    now: datetime | None = None,
    on_collected: Callable[[str, Any], None] | None = None,
) -> dict[str, Any]:
    """Collect each source independently; failures never discard successful sources."""
    run_time = now or datetime.now(UTC)
    gathered: dict[str, Any] = {}
    failures: dict[str, str] = {}
    flags: set[str] = set()
    for collector in collectors:
        try:
            payload = collector.collect()
            safe_payload, payload_flags = redact(payload)
            gathered[collector.name] = safe_payload
            flags.update(payload_flags)
            if on_collected:
                on_collected(collector.name, safe_payload)
        except CollectorError as exc:
            failures[collector.name] = exc.summary()
        except Exception as exc:  # noqa: BLE001 - isolates source failure, hides exception text.
            failures[collector.name] = f"source unavailable ({type(exc).__name__})"

    return {
        "run": run_metadata(run_time, failures),
        "sources": gathered,
        "redaction_flags": sorted(flags),
    }


def write_data_file(path: Path, collected: dict[str, Any]) -> None:
    """Redact once more, then atomically persist data.json with private permissions."""
    safe_payload, _ = redact(collected)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(safe_payload, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
