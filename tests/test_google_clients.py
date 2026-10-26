import base64
import json
from email import message_from_bytes
from email.policy import default

import httpx
import pytest

from sb.clients.google import CalendarClient, DriveClient, GmailClient, GoogleTokenProvider


def test_google_token_provider_refreshes_and_caches_token_without_logging_secrets():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"access_token": "test-access-token", "expires_in": 3600})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GoogleTokenProvider(
        "parcel",
        client_id="test-client",
        client_secret="test-client-secret",
        refresh_token="test-refresh-token",
        client=client,
        clock=lambda: 100.0,
    )
    assert provider.access_token() == "test-access-token"
    assert provider.access_token() == "test-access-token"
    assert len(requests) == 1
    assert requests[0].url.host == "oauth2.googleapis.com"
    assert "test-refresh-token" in requests[0].read().decode()


def test_gmail_listing_tags_account_and_draft_creates_draft_resource_only():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/messages") and request.method == "GET":
            return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}]})
        if request.url.path.endswith("/drafts") and request.method == "POST":
            return httpx.Response(200, json={"id": "draft1"})
        return httpx.Response(404, json={})

    api = GmailClient(
        "personal",
        token_source=type("Token", (), {"access_token": lambda self: "fake"})(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert api.list_messages(query="is:unread") == [
        {"id": "m1", "threadId": "t1", "account": "personal"}
    ]
    assert api.create_reply_draft(
        thread_id="t1", to="guest@example.test", subject="Re: Hi", body="Draft only"
    ) == {"id": "draft1", "account": "personal"}
    draft_request = requests[-1]
    assert draft_request.url.path.endswith("/drafts")
    payload = json.loads(draft_request.read())
    raw = payload["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    message = message_from_bytes(decoded, policy=default)
    assert message["To"] == "guest@example.test"
    assert payload["message"]["threadId"] == "t1"
    assert all("/send" not in request.url.path for request in requests)


def test_gmail_thread_read_extracts_headers_and_text_body():
    requests = []
    body = base64.urlsafe_b64encode(b"Hello from a fake thread").decode().rstrip("=")

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "messages": [
                    {
                        "id": "m1",
                        "threadId": "t1",
                        "internalDate": "1793040000000",
                        "payload": {
                            "mimeType": "text/plain",
                            "headers": [{"name": "Subject", "value": "Fake subject"}],
                            "body": {"data": body},
                        },
                    }
                ]
            },
        )

    api = GmailClient(
        "parcel",
        token_source=type("Token", (), {"access_token": lambda self: "fake"})(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    thread = api.get_thread("thread/with/slash")
    assert thread[0]["body"] == "Hello from a fake thread"
    assert thread[0]["headers"]["subject"] == "Fake subject"
    assert thread[0]["account"] == "parcel"
    assert b"%2F" in requests[0].url.raw_path


def test_gmail_labels_can_only_be_added_under_sb_namespace():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"labels": []})
        if request.url.path.endswith("/labels"):
            return httpx.Response(200, json={"id": "Label_1"})
        return httpx.Response(200, json={})

    api = GmailClient(
        "parcel",
        token_source=type("Token", (), {"access_token": lambda self: "fake"})(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ValueError, match="SB/"):
        api.add_sb_label(message_id="m1", label="Important")
    api.add_sb_label(message_id="m1", label="SB/Reported")
    modify = json.loads(requests[-1].read())
    assert modify == {"addLabelIds": ["Label_1"]}
    assert "removeLabelIds" not in modify


def test_calendar_writes_only_primary_owned_event_and_sb_blocks_have_no_attendees():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200, json={"id": "event1", "status": "confirmed", "organizer": {"self": True}}
            )
        if request.method == "PATCH":
            return httpx.Response(200, json={"id": "event1"})
        return httpx.Response(200, json={"id": "block1"})

    calendar = CalendarClient(
        "personal",
        token_source=type("Token", (), {"access_token": lambda self: "fake"})(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert calendar.set_busy("event1") == {"calendar_id": "primary", "event_id": "event1"}
    assert requests[-1].method == "PATCH"
    assert json.loads(requests[-1].read()) == {"transparency": "opaque"}
    assert calendar.create_block(
        title="SB: Focus", start="2026-10-26T09:00:00-05:00", end="2026-10-26T10:00:00-05:00"
    ) == {"event_id": "block1", "calendar_id": "primary"}
    block_payload = json.loads(requests[-1].read())
    assert block_payload["summary"] == "SB: Focus"
    assert "attendees" not in block_payload
    assert requests[-1].url.path == "/calendar/v3/calendars/primary/events"


def test_calendar_refuses_cancelled_event_and_invalid_block_without_writes():
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(
            200,
            json={"id": "event1", "status": "cancelled", "organizer": {"self": False}},
        )

    calendar = CalendarClient(
        "personal",
        token_source=type("Token", (), {"access_token": lambda self: "fake"})(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ValueError, match="existing, active"):
        calendar.set_busy("shared-event")
    with pytest.raises(ValueError, match="SB:"):
        calendar.create_block(
            title="Focus", start="2026-10-26T09:00:00Z", end="2026-10-26T10:00:00Z"
        )
    assert methods == ["GET"]


def test_drive_client_paginates_read_only_file_metadata():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.params.get("pageToken") == "page2":
            return httpx.Response(200, json={"files": [{"id": "f2", "name": "fake2"}]})
        return httpx.Response(
            200, json={"files": [{"id": "f1", "name": "fake1"}], "nextPageToken": "page2"}
        )

    drive = DriveClient(
        token_source=type("Token", (), {"access_token": lambda self: "fake"})(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert drive.list_files() == [{"id": "f1", "name": "fake1"}, {"id": "f2", "name": "fake2"}]
    assert len(requests) == 2
    assert all(request.method == "GET" for request in requests)


def test_drive_client_can_read_text_content_without_write_methods():
    def handler(request):
        assert request.method == "GET"
        assert request.url.params["alt"] == "media"
        return httpx.Response(200, text="fake read-only document")

    drive = DriveClient(
        token_source=type("Token", (), {"access_token": lambda self: "fake"})(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert drive.get_text_file("file-id") == "fake read-only document"
