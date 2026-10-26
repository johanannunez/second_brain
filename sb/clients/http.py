"""HTTP primitives with bounded timeouts, safe errors, and read retry behavior."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx


class APIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JsonHTTPClient:
    """JSON transport. Only idempotent GET requests retry automatically."""

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str] | None = None,
        timeout: float = 15.0,
        retries: int = 1,
        backoff_seconds: float = 0.5,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("provider base URL must use HTTPS")
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout), headers=headers)
        if client is not None and headers:
            self._client.headers.update(headers)
        self._retries = max(0, retries)
        self._backoff = max(0.0, backoff_seconds)
        self._sleep = sleep

    def close(self) -> None:
        self._client.close()

    def set_header(self, name: str, value: str) -> None:
        self._client.headers[name] = value

    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def get_text(self, path: str, *, params: Mapping[str, Any] | None = None) -> str:
        response = self._request("GET", path, params=params, raw_response=True)
        return response.text

    def post_json(self, path: str, *, json_body: Mapping[str, Any]) -> Any:
        # Non-idempotent writes do not retry automatically. Callers must use a
        # provider idempotency key before adding retries for any write endpoint.
        return self._request("POST", path, json_body=json_body, retryable=False)

    def post_form(self, path: str, *, form_data: Mapping[str, str]) -> Any:
        """Send one non-retried form POST, used for OAuth token refresh."""
        return self._request("POST", path, form_body=form_data, retryable=False)

    def post_no_content(self, path: str, *, json_body: Mapping[str, Any] | None = None) -> None:
        """Send one non-retried write whose provider contract has no JSON body."""
        self._request("POST", path, json_body=json_body, retryable=False, raw_response=True)

    def patch_json(self, path: str, *, json_body: Mapping[str, Any]) -> Any:
        return self._request("PATCH", path, json_body=json_body, retryable=False)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        form_body: Mapping[str, str] | None = None,
        retryable: bool | None = None,
        raw_response: bool = False,
    ) -> Any:
        if path.startswith("http://") or path.startswith("https://") or ".." in path.split("/"):
            raise ValueError("provider path must be relative to its configured HTTPS base URL")
        should_retry = method == "GET" if retryable is None else retryable
        max_attempts = 1 + (self._retries if should_retry else 0)
        url = f"{self.base_url}/{path.lstrip('/')}"
        response: httpx.Response | None = None
        for attempt in range(max_attempts):
            try:
                response = self._client.request(
                    method, url, params=params, json=json_body, data=form_body
                )
            except httpx.TimeoutException as exc:
                if should_retry and attempt + 1 < max_attempts:
                    self._sleep(self._backoff * (2**attempt))
                    continue
                raise APIError("provider request timed out") from exc
            except httpx.RequestError as exc:
                if should_retry and attempt + 1 < max_attempts:
                    self._sleep(self._backoff * (2**attempt))
                    continue
                raise APIError("provider request failed") from exc
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if should_retry and attempt + 1 < max_attempts:
                    self._sleep(self._retry_delay(response, attempt))
                    continue
            break

        assert response is not None
        if not 200 <= response.status_code < 300:
            raise APIError("provider rejected request", status_code=response.status_code)
        if raw_response:
            return response
        try:
            return response.json()
        except ValueError as exc:
            raise APIError(
                "provider returned invalid JSON", status_code=response.status_code
            ) from exc

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After", "")
        try:
            return min(30.0, max(0.0, float(retry_after)))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                seconds = (retry_at - datetime.now(UTC)).total_seconds()
                return min(30.0, max(0.0, seconds))
            except (TypeError, ValueError, OverflowError):
                return self._backoff * (2**attempt)
