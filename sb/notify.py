"""Slack DM client that can address only Jo's configured user ID."""

from __future__ import annotations

import os

import httpx

from sb.clients.http import JsonHTTPClient


class SlackNotifier:
    def __init__(
        self,
        *,
        token: str | None = None,
        user_id: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token if token is not None else os.environ.get("SLACK_BOT_TOKEN", "")
        self._user_id = user_id if user_id is not None else os.environ.get("SLACK_JO_USER_ID", "")
        self._http = JsonHTTPClient(
            base_url="https://slack.com/api",
            headers={"Authorization": f"Bearer {self._token}"} if self._token else {},
            client=client,
        )

    def notify_jo(self, text: str) -> dict[str, object]:
        if not self._token or not self._user_id:
            raise RuntimeError("Slack notification credentials are not configured")
        if not text.strip():
            raise ValueError("notification text cannot be empty")
        response = self._http.post_json(
            "/chat.postMessage",
            json_body={"channel": self._user_id, "text": text},
        )
        if response.get("ok") is not True:
            raise RuntimeError("Slack notification was rejected")
        return {"ok": True}
