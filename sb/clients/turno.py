"""Turno API v2 client for the documented project and unresolved-problem reads."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from sb.clients.http import APIError, JsonHTTPClient


class TurnoClient:
    BASE_URL = "https://api.turnoverbnb.com/v2"

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        partner_id: str | None = None,
        client: httpx.Client | None = None,
        sleep=None,
    ) -> None:
        secret_key = (
            secret_key if secret_key is not None else os.environ.get("TURNO_SECRET_KEY", "")
        )
        partner_id = (
            partner_id if partner_id is not None else os.environ.get("TURNO_PARTNER_ID", "")
        )
        headers = {"Accept": "application/json"}
        if secret_key:
            headers["Authorization"] = f"Bearer {secret_key}"
        if partner_id:
            headers["TBNB-Partner-ID"] = partner_id
        kwargs: dict[str, Any] = {"base_url": self.BASE_URL, "headers": headers, "client": client}
        if sleep is not None:
            kwargs["sleep"] = sleep
        self._http = JsonHTTPClient(**kwargs)

    def projects(self, *, start: str, end: str) -> list[dict[str, Any]]:
        if not start or not end:
            raise ValueError("start and end are required for Turno project reads")
        return self._paginate("/projects", {"start": start, "end": end})

    def unresolved_problems(self) -> list[dict[str, Any]]:
        return self._paginate("/problems", {"status": "unresolved"})

    def _paginate(self, path: str, params: Mapping[str, str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        cursor: str | None = None
        seen: set[tuple[str, str]] = set()
        for _ in range(1000):
            request_params = dict(params)
            if cursor:
                request_params["cursor"] = cursor
            elif page > 1:
                request_params["page"] = str(page)
            payload = self._http.get_json(path, params=request_params)
            items, next_cursor, next_page, has_more = self._page_parts(payload)
            if not all(isinstance(item, dict) for item in items):
                raise APIError("Turno returned an unexpected page shape")
            results.extend(items)
            if next_cursor:
                marker = ("cursor", next_cursor)
                if marker in seen:
                    raise APIError("Turno pagination cursor repeated")
                seen.add(marker)
                cursor = next_cursor
                page = 1
            elif next_page:
                marker = ("page", str(next_page))
                if marker in seen:
                    raise APIError("Turno pagination page repeated")
                seen.add(marker)
                page = int(next_page)
                cursor = None
            elif has_more:
                page += 1
                cursor = None
            else:
                return results
        raise APIError("Turno pagination limit exceeded")

    @staticmethod
    def _page_parts(payload: Any) -> tuple[list[Any], str | None, str | None, bool]:
        if isinstance(payload, list):
            return payload, None, None, False
        if not isinstance(payload, dict):
            raise APIError("Turno returned an unexpected page shape")
        items = payload.get("results", payload.get("data", []))
        if not isinstance(items, list):
            raise APIError("Turno returned an unexpected results value")
        pagination = payload.get("pagination", {})
        if not isinstance(pagination, dict):
            pagination = {}
        cursor = payload.get("next_cursor", pagination.get("next_cursor"))
        next_page = payload.get("next_page", pagination.get("next_page"))
        has_more = bool(payload.get("has_more", pagination.get("has_more", False)))
        return (
            items,
            str(cursor) if cursor else None,
            str(next_page) if next_page else None,
            has_more,
        )
