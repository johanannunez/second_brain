"""Google OAuth and narrow Gmail, Calendar, and Drive clients."""

from __future__ import annotations

import base64
import os
import time
from collections.abc import Mapping
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from sb.clients.http import APIError, JsonHTTPClient


class TokenSource(Protocol):
    def access_token(self) -> str: ...


class GoogleTokenProvider:
    """Refresh access tokens in memory; secrets are read only from named env vars."""

    TOKEN_URL = "https://oauth2.googleapis.com"

    def __init__(
        self,
        account: str,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        client: httpx.Client | None = None,
        clock=time.monotonic,
    ) -> None:
        if account not in {"parcel", "personal"}:
            raise ValueError("Google account must be parcel or personal")
        self.account = account
        self._client_id = (
            client_id if client_id is not None else os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
        )
        self._client_secret = (
            client_secret
            if client_secret is not None
            else os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
        )
        self._refresh_token = (
            refresh_token
            if refresh_token is not None
            else os.environ.get(f"GOOGLE_REFRESH_TOKEN_{account.upper()}", "")
        )
        self._http = JsonHTTPClient(base_url=self.TOKEN_URL, client=client)
        self._clock = clock
        self._access_token = ""
        self._expires_at = 0.0

    def access_token(self) -> str:
        if self._access_token and self._clock() < self._expires_at - 30:
            return self._access_token
        missing = [
            name
            for name, value in (
                ("GOOGLE_OAUTH_CLIENT_ID", self._client_id),
                ("GOOGLE_OAUTH_CLIENT_SECRET", self._client_secret),
                (f"GOOGLE_REFRESH_TOKEN_{self.account.upper()}", self._refresh_token),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Google credentials are not configured: {', '.join(missing)}")
        try:
            payload = self._http.post_form(
                "/token",
                form_data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except APIError as exc:
            raise RuntimeError("Google access-token refresh failed") from exc
        token = payload.get("access_token") if isinstance(payload, dict) else None
        expires_in = payload.get("expires_in", 3600) if isinstance(payload, dict) else 0
        if not isinstance(token, str) or not token or not isinstance(expires_in, (int, float)):
            raise RuntimeError("Google returned an invalid access-token response")
        self._access_token = token
        self._expires_at = self._clock() + float(expires_in)
        return token


class _GoogleAPI:
    def __init__(
        self,
        *,
        base_url: str,
        token_source: TokenSource,
        client: httpx.Client | None = None,
        sleep=None,
    ) -> None:
        kwargs: dict[str, Any] = {"base_url": base_url, "client": client}
        if sleep is not None:
            kwargs["sleep"] = sleep
        self._http = JsonHTTPClient(**kwargs)
        self._token_source = token_source

    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        self._authorize()
        return self._http.get_json(path, params=params)

    def post_json(self, path: str, *, json_body: Mapping[str, Any]) -> Any:
        self._authorize()
        return self._http.post_json(path, json_body=json_body)

    def patch_json(self, path: str, *, json_body: Mapping[str, Any]) -> Any:
        self._authorize()
        return self._http.patch_json(path, json_body=json_body)

    def get_text(self, path: str, *, params: Mapping[str, Any] | None = None) -> str:
        self._authorize()
        return self._http.get_text(path, params=params)

    def _authorize(self) -> None:
        self._http.set_header("Authorization", f"Bearer {self._token_source.access_token()}")


class GmailClient:
    BASE_URL = "https://gmail.googleapis.com"

    def __init__(
        self, account: str, *, token_source: TokenSource, client: httpx.Client | None = None
    ):
        self.account = account
        self._api = _GoogleAPI(base_url=self.BASE_URL, token_source=token_source, client=client)

    def list_messages(self, *, query: str = "", max_results: int = 100) -> list[dict[str, str]]:
        if not 1 <= max_results <= 500:
            raise ValueError("max_results must be between 1 and 500")
        results: list[dict[str, str]] = []
        page_token: str | None = None
        while len(results) < max_results:
            params: dict[str, Any] = {"maxResults": min(100, max_results - len(results))}
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token
            payload = self._api.get_json("/gmail/v1/users/me/messages", params=params)
            messages = payload.get("messages", []) if isinstance(payload, dict) else []
            results.extend(
                {"id": str(item["id"]), "threadId": str(item["threadId"])}
                for item in messages
                if "id" in item
            )
            page_token = payload.get("nextPageToken") if isinstance(payload, dict) else None
            if not page_token or not messages:
                break
        return [{**item, "account": self.account} for item in results[:max_results]]

    def get_message(self, message_id: str) -> dict[str, Any]:
        payload = self._api.get_json(
            f"/gmail/v1/users/me/messages/{quote(message_id, safe='')}",
            params={"format": "full"},
        )
        if not isinstance(payload, dict):
            raise APIError("Gmail returned an unexpected message shape")
        return self._normalize_message(payload)

    def get_thread(self, thread_id: str) -> list[dict[str, Any]]:
        payload = self._api.get_json(
            f"/gmail/v1/users/me/threads/{quote(thread_id, safe='')}",
            params={"format": "full"},
        )
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        return [self._normalize_message(item) for item in messages if isinstance(item, dict)]

    def _normalize_message(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", {})
        headers = payload.get("headers", []) if isinstance(payload, dict) else []
        normalized_headers = {
            str(item.get("name", "")).lower(): str(item.get("value", ""))
            for item in headers
            if isinstance(item, dict) and item.get("name")
        }
        return {
            "id": str(message.get("id", "")),
            "thread_id": str(message.get("threadId", "")),
            "account": self.account,
            "internal_date": message.get("internalDate"),
            "snippet": message.get("snippet", ""),
            "headers": normalized_headers,
            "body": self._message_body(payload),
            "labels": [str(label) for label in message.get("labelIds", [])],
        }

    @classmethod
    def _message_body(cls, part: Any) -> str:
        if not isinstance(part, dict):
            return ""
        body = part.get("body", {})
        data = body.get("data") if isinstance(body, dict) else None
        if data and part.get("mimeType") == "text/plain":
            try:
                return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                    "utf-8", errors="replace"
                )
            except (ValueError, UnicodeError):
                return ""
        child_parts = part.get("parts", [])
        if isinstance(child_parts, list):
            plain = [cls._message_body(child) for child in child_parts]
            return "\n".join(text for text in plain if text)
        if data:
            try:
                return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                    "utf-8", errors="replace"
                )
            except (ValueError, UnicodeError):
                return ""
        return ""

    def create_reply_draft(
        self, *, thread_id: str, to: str, subject: str, body: str
    ) -> dict[str, Any]:
        if not all((thread_id, to, subject, body)):
            raise ValueError("thread_id, recipient, subject, and body are required for a draft")
        email = EmailMessage()
        email["To"] = to
        email["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        email.set_content(body)
        raw = base64.urlsafe_b64encode(email.as_bytes()).decode("ascii").rstrip("=")
        payload = self._api.post_json(
            "/gmail/v1/users/me/drafts",
            json_body={"message": {"raw": raw, "threadId": thread_id}},
        )
        if not isinstance(payload, dict):
            raise APIError("Gmail returned an unexpected draft response")
        return {"id": str(payload.get("id", "")), "account": self.account}

    def add_sb_label(self, *, message_id: str, label: str) -> None:
        if not label.startswith("SB/"):
            raise ValueError("only labels beginning with SB/ may be applied")
        payload = self._api.get_json("/gmail/v1/users/me/labels")
        labels = payload.get("labels", []) if isinstance(payload, dict) else []
        label_id = next((item["id"] for item in labels if item.get("name") == label), None)
        if not label_id:
            created = self._api.post_json(
                "/gmail/v1/users/me/labels",
                json_body={
                    "name": label,
                    "labelListVisibility": "labelHide",
                    "messageListVisibility": "hide",
                },
            )
            label_id = created.get("id") if isinstance(created, dict) else None
        if not label_id:
            raise APIError("Gmail did not return a label identifier")
        self._api.post_json(
            f"/gmail/v1/users/me/messages/{quote(message_id, safe='')}/modify",
            json_body={"addLabelIds": [label_id]},
        )


class CalendarClient:
    BASE_URL = "https://www.googleapis.com"

    def __init__(
        self, account: str, *, token_source: TokenSource, client: httpx.Client | None = None
    ):
        self.account = account
        self._api = _GoogleAPI(base_url=self.BASE_URL, token_source=token_source, client=client)

    def list_calendars(self) -> list[dict[str, Any]]:
        return self._paginate("/calendar/v3/users/me/calendarList", "items")

    def list_events(
        self,
        calendar_id: str,
        *,
        time_min: str | None = None,
        time_max: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"singleEvents": "true", "orderBy": "startTime"}
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        events = self._paginate(
            f"/calendar/v3/calendars/{quote(calendar_id, safe='')}/events", "items", params
        )
        return [
            {
                **event,
                "calendar_id": calendar_id,
                "owned_by_user": bool(event.get("organizer", {}).get("self")),
                "account": self.account,
            }
            for event in events
        ]

    def snapshot(
        self, *, time_min: str | None = None, time_max: str | None = None
    ) -> dict[str, Any]:
        calendars = self.list_calendars()
        primary = next((item for item in calendars if item.get("primary") is True), None)
        if not isinstance(primary, dict) or not primary.get("id"):
            raise APIError("Google Calendar did not identify a primary calendar")
        all_events: list[dict[str, Any]] = []
        for calendar in calendars:
            calendar_id = calendar.get("id")
            if isinstance(calendar_id, str) and calendar_id:
                events = self.list_events(calendar_id, time_min=time_min, time_max=time_max)
                for event in events:
                    event["owned_by_user"] = calendar_id == primary["id"]
                all_events.extend(events)
        return {
            "primary_calendar_id": str(primary["id"]),
            "calendars": calendars,
            "events": all_events,
            "account": self.account,
        }

    def set_busy(self, event_id: str) -> dict[str, str]:
        encoded_id = quote(event_id, safe="")
        event = self._api.get_json(f"/calendar/v3/calendars/primary/events/{encoded_id}")
        if not isinstance(event, dict) or event.get("status") == "cancelled":
            raise ValueError("only an existing, active primary-calendar event may be marked busy")
        self._api.patch_json(
            f"/calendar/v3/calendars/primary/events/{encoded_id}",
            json_body={"transparency": "opaque"},
        )
        return {"calendar_id": "primary", "event_id": event_id}

    def create_block(self, *, title: str, start: str, end: str) -> dict[str, str]:
        if not title.startswith("SB:"):
            raise ValueError("calendar blocks must have an SB: title")
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if start_dt.tzinfo is None or end_dt.tzinfo is None or end_dt <= start_dt:
            raise ValueError("calendar block needs timezone-aware start and later end")
        event = self._api.post_json(
            "/calendar/v3/calendars/primary/events",
            json_body={
                "summary": title,
                "start": {"dateTime": start_dt.isoformat()},
                "end": {"dateTime": end_dt.isoformat()},
                "transparency": "opaque",
            },
        )
        return {"event_id": str(event.get("id", "")), "calendar_id": "primary"}

    def _paginate(
        self,
        path: str,
        key: str,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            query = dict(params or {})
            query["maxResults"] = 250
            if page_token:
                query["pageToken"] = page_token
            payload = self._api.get_json(path, params=query)
            items = payload.get(key, []) if isinstance(payload, dict) else []
            results.extend(item for item in items if isinstance(item, dict))
            page_token = payload.get("nextPageToken") if isinstance(payload, dict) else None
            if not page_token:
                return results


class DriveClient:
    BASE_URL = "https://www.googleapis.com"

    def __init__(self, *, token_source: TokenSource, client: httpx.Client | None = None):
        self._api = _GoogleAPI(base_url=self.BASE_URL, token_source=token_source, client=client)

    def list_files(self, *, query: str | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "pageSize": 1000,
                "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink)",
            }
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token
            payload = self._api.get_json("/drive/v3/files", params=params)
            files = payload.get("files", []) if isinstance(payload, dict) else []
            results.extend(item for item in files if isinstance(item, dict))
            page_token = payload.get("nextPageToken") if isinstance(payload, dict) else None
            if not page_token:
                return results

    def get_text_file(self, file_id: str) -> str:
        return self._api.get_text(
            f"/drive/v3/files/{quote(file_id, safe='')}", params={"alt": "media"}
        )
