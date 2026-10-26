"""Hospitable reservation-thread retry and per-run deduplication policy.

Endpoint paths are intentionally injected until they can be checked against the
provider's current public API documentation.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sb.clients.http import APIError


@dataclass(frozen=True)
class ThreadRead:
    reviewed: bool
    payload: Any = None
    note: str | None = None


class HospitableThreadReads:
    def __init__(self, *, sleep: Callable[[float], None] = time.sleep):
        self._sleep = sleep
        self._fetched: dict[str, ThreadRead] = {}

    def fetch_once_per_run(
        self,
        reservation_id: str,
        fetch: Callable[[], Any],
    ) -> ThreadRead:
        if not reservation_id:
            raise ValueError("reservation_id is required")
        if reservation_id in self._fetched:
            return self._fetched[reservation_id]
        try:
            result = ThreadRead(reviewed=True, payload=fetch())
        except APIError as first_error:
            if first_error.status_code != 429:
                raise
            self._sleep(30)
            try:
                result = ThreadRead(reviewed=True, payload=fetch())
            except APIError as retry_error:
                if retry_error.status_code != 429:
                    raise
                result = ThreadRead(
                    reviewed=False,
                    note="not reviewed after rate limit; retry once next run",
                )
        self._fetched[reservation_id] = result
        return result
