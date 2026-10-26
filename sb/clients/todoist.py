"""Todoist API v1 client, including its results/next_cursor pagination shape."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from sb.actions import TodoistComplete, validate_action_context
from sb.clients.http import APIError, JsonHTTPClient


class TodoistClient:
    BASE_URL = "https://api.todoist.com/api/v1"

    def __init__(
        self, *, token: str | None = None, client: httpx.Client | None = None, sleep=None
    ) -> None:
        token = token if token is not None else os.environ.get("TODOIST_API_TOKEN", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        kwargs: dict[str, Any] = {"base_url": self.BASE_URL, "headers": headers, "client": client}
        if sleep is not None:
            kwargs["sleep"] = sleep
        self._http = JsonHTTPClient(**kwargs)

    def projects(self) -> list[dict[str, Any]]:
        return self._paginate("/projects", {})

    def tasks(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        params = {"project_id": project_id} if project_id else {}
        return self._paginate("/tasks", params)

    def completed_tasks(self, *, since: str, until: str) -> list[dict[str, Any]]:
        return self._paginate(
            "/tasks/completed/by_completion_date",
            {"since": since, "until": until},
        )

    def create_task(
        self,
        *,
        content: str,
        due_string: str | None = None,
        description: str = "",
        label: str,
    ) -> dict[str, Any]:
        if not content.strip() or label != "sb":
            raise ValueError("Todoist task creation requires content and the sb label")
        body: dict[str, Any] = {"content": content, "description": description, "labels": ["sb"]}
        if due_string:
            body["due_string"] = due_string
        payload = self._http.post_json("/tasks", json_body=body)
        if not isinstance(payload, dict):
            raise APIError("Todoist returned an unexpected task response")
        return {"id": str(payload.get("id", ""))}

    def complete_task(
        self,
        action: TodoistComplete,
        *,
        source_data: dict[str, object],
    ) -> None:
        errors = validate_action_context([action], source_data)
        if errors:
            raise ValueError("; ".join(errors))
        self._http.post_no_content(f"/tasks/{quote(action.task_id, safe='')}/close")

    def _paginate(self, path: str, params: Mapping[str, str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(1000):
            request_params = dict(params)
            if cursor:
                request_params["cursor"] = cursor
            payload = self._http.get_json(path, params=request_params)
            if isinstance(payload, list):
                items, next_cursor = payload, None
            elif isinstance(payload, dict):
                items = payload.get("results")
                next_cursor = payload.get("next_cursor")
                if not isinstance(items, list):
                    raise APIError("Todoist returned an unexpected results value")
            else:
                raise APIError("Todoist returned an unexpected page shape")
            if not all(isinstance(item, dict) for item in items):
                raise APIError("Todoist returned an unexpected item shape")
            results.extend(items)
            if not next_cursor:
                return results
            cursor = str(next_cursor)
            if cursor in seen:
                raise APIError("Todoist pagination cursor repeated")
            seen.add(cursor)
        raise APIError("Todoist pagination limit exceeded")
