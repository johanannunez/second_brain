import json

import httpx
import pytest

from sb.clients.http import APIError, JsonHTTPClient
from sb.clients.todoist import TodoistClient
from sb.clients.turno import TurnoClient
from sb.notify import SlackNotifier


def test_safe_get_retries_once_on_5xx_and_does_not_expose_body():
    attempts = []
    delays = []

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503, json={"detail": "secret response should not leak"})
        return httpx.Response(200, json={"ok": True})

    client = JsonHTTPClient(
        base_url="https://example.test/api",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=delays.append,
    )
    assert client.get_json("/items") == {"ok": True}
    assert len(attempts) == 2
    assert delays == [0.5]


def test_non_idempotent_post_does_not_retry_automatically():
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(503, json={"detail": "private"})

    client = JsonHTTPClient(
        base_url="https://example.test/api",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(APIError, match="provider rejected request"):
        client.post_json("/messages", json_body={"text": "fake"})
    assert len(attempts) == 1


def test_todoist_client_uses_v1_and_follows_next_cursor():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.params.get("cursor") == "cursor-2":
            return httpx.Response(200, json={"results": [{"id": "p2"}], "next_cursor": None})
        return httpx.Response(200, json={"results": [{"id": "p1"}], "next_cursor": "cursor-2"})

    client = TodoistClient(
        token="test-token-not-real",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.projects() == [{"id": "p1"}, {"id": "p2"}]
    assert [request.url.path for request in requests] == ["/api/v1/projects", "/api/v1/projects"]
    assert requests[0].headers["Authorization"] == "Bearer test-token-not-real"
    assert requests[1].url.params["cursor"] == "cursor-2"


def test_todoist_write_surface_only_creates_sb_tasks_and_completes_with_run_evidence():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/v1/tasks":
            return httpx.Response(200, json={"id": "new-task"})
        return httpx.Response(204)

    client = TodoistClient(
        token="test-token-not-real",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.create_task(content="Fake follow-up", description="Fixture", label="sb") == {
        "id": "new-task"
    }
    create_payload = json.loads(requests[0].read())
    assert create_payload["labels"] == ["sb"]
    with pytest.raises(ValueError, match="sb label"):
        client.create_task(content="Fake", label="other")

    from sb.actions import TodoistComplete

    action = TodoistComplete(
        type="todoist_complete",
        task_id="task-1",
        proof_source="google_calendar",
        proof_detail="Meeting completion visible in this run",
    )
    source_data = {
        "sources": {
            "todoist": {"open_tasks": [{"id": "task-1"}]},
            "google_calendar": {"events": [{"id": "event-1"}]},
        }
    }
    client.complete_task(action, source_data=source_data)
    assert requests[-1].url.path == "/api/v1/tasks/task-1/close"


def test_todoist_completion_is_rejected_without_evidence_from_this_run():
    from sb.actions import TodoistComplete

    client = TodoistClient(
        token="test-token-not-real",
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    action = TodoistComplete(
        type="todoist_complete",
        task_id="task-1",
        proof_source="email",
        proof_detail="Model claim without source",
    )
    with pytest.raises(ValueError, match="must reference an open task"):
        client.complete_task(action, source_data={"sources": {}})


def test_turno_client_sends_required_headers_and_follows_pages():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"data": [{"id": "p2"}]})
        return httpx.Response(200, json={"data": [{"id": "p1"}], "pagination": {"next_page": 2}})

    client = TurnoClient(
        secret_key="test-key-not-real",
        partner_id="test-partner",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.projects(start="2026-10-26", end="2026-10-27") == [{"id": "p1"}, {"id": "p2"}]
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].headers["Authorization"] == "Bearer test-key-not-real"
    assert requests[0].headers["TBNB-Partner-Id"] == "test-partner"
    assert requests[1].url.params["page"] == "2"


def test_slack_notifier_only_sends_to_configured_jo_user():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notify = SlackNotifier(token="test-token-not-real", user_id="U-JO", client=client)
    assert notify.notify_jo("All clear") == {"ok": True}
    assert requests[0].url.path.endswith("/chat.postMessage")
    assert requests[0].read().decode().find('"channel":"U-JO"') >= 0
