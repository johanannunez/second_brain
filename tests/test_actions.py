import pytest
from pydantic import ValidationError

from sb.actions import (
    approval_event_allowed,
    parse_actions,
    validate_action_context,
    validate_file_changes,
)
from sb.apply import execute_actions, validate_run, write_worker_files


def test_worker_action_allowlist_rejects_unknown_and_unapproved_types():
    with pytest.raises(ValidationError):
        parse_actions([{"type": "send_email", "body": "hello"}], "morning-briefing")
    with pytest.raises(ValueError, match="cannot use"):
        parse_actions(
            [
                {
                    "type": "gmail_label",
                    "account": "parcel",
                    "message_id": "m1",
                    "label": "SB/Reported",
                }
            ],
            "monthly-close",
        )


def test_action_schema_rejects_extra_fields_and_non_sb_labels():
    with pytest.raises(ValidationError):
        parse_actions(
            [{"type": "notify", "text": "All clear", "channel": "someone-else"}], "weekly-review"
        )
    with pytest.raises(ValidationError):
        parse_actions(
            [
                {
                    "type": "gmail_label",
                    "account": "parcel",
                    "message_id": "m1",
                    "label": "important",
                }
            ],
            "morning-briefing",
        )


def test_outbox_requires_provider_id_and_rejects_sensitive_message_content():
    base = {
        "type": "outbox_message",
        "channel": "quo",
        "recipient_id": "conversation-id-1",
        "message": "Thanks, I will follow up tomorrow.",
        "reason": "Jo needs to approve this reply.",
    }
    actions = parse_actions(
        [base, {"type": "notify", "text": "Queued for approval."}], "midday-sweep"
    )
    assert len(actions) == 2
    with pytest.raises(ValidationError, match="provider ID"):
        parse_actions([{**base, "recipient_id": "guest@example.test"}], "midday-sweep")
    with pytest.raises(ValidationError, match="sensitive value"):
        parse_actions([{**base, "message": "Your door code is 4482."}], "midday-sweep")


def test_notify_rejects_sensitive_content():
    with pytest.raises(ValidationError, match="sensitive value"):
        parse_actions([{"type": "notify", "text": "Door code is 4482."}], "midday-sweep")


def test_gmail_drafts_and_todoist_actions_reject_sensitive_text():
    with pytest.raises(ValidationError, match="sensitive value"):
        parse_actions(
            [
                {
                    "type": "gmail_draft",
                    "account": "parcel",
                    "thread_id": "thread-1",
                    "subject": "Re: Stay",
                    "body": "The lockbox code is 9999.",
                }
            ],
            "midday-sweep",
        )
    with pytest.raises(ValidationError, match="sensitive value"):
        parse_actions(
            [{"type": "todoist_create", "content": "Call guest at 605-555-0100", "label": "sb"}],
            "evening-check-in",
        )


def test_worker_specific_file_allowlists_block_deletions_and_protected_paths():
    assert validate_file_changes("morning-briefing", {"daily/2026-10-26-briefing.md": "safe"}) == []
    errors = validate_file_changes(
        "morning-briefing",
        {
            "AGENTS.md": "changed",
            "sb/apply.py": "changed",
            "dashboard/today.md": None,
            "../profile.md": "changed",
            "profile.md": "changed",
        },
    )
    assert len(errors) == 5
    assert any("protected path: AGENTS.md" in error for error in errors)
    assert any("deletions are forbidden" in error for error in errors)
    assert any("invalid path" in error for error in errors)


def test_worker_file_apply_is_scoped_atomic_and_redacts_before_persisting(tmp_path):
    written = write_worker_files(
        tmp_path,
        "morning-briefing",
        {"daily/briefing.md": "Door code: 7171\nAll clear.\n"},
    )
    assert written == ["daily/briefing.md"]
    assert (tmp_path / "daily/briefing.md").read_text() == "Door code: [REDACTED]\nAll clear.\n"
    with pytest.raises(ValueError, match="outside"):
        write_worker_files(
            tmp_path,
            "morning-briefing",
            {"daily/should-not-exist.md": "safe", "profile.md": "outside scope"},
        )
    assert not (tmp_path / "daily/should-not-exist.md").exists()


def test_worker_file_apply_refuses_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside-second-brain"
    outside.mkdir()
    (tmp_path / "dashboard").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        write_worker_files(tmp_path, "morning-briefing", {"dashboard/today.md": "safe"})
    assert not (outside / "today.md").exists()


def test_approval_sender_check_requires_jo_to_add_approved_to_unsent_outbox_issue():
    base = {"outbox", "approved"}
    args = {"event_action": "labeled", "event_label": "approved", "issue_labels": base}
    assert approval_event_allowed(sender="johanannunez", **args)
    assert not approval_event_allowed(sender="someone-else", **args)
    assert not approval_event_allowed(sender="johanannunez", **{**args, "event_action": "opened"})
    assert not approval_event_allowed(
        sender="johanannunez", **{**args, "issue_labels": {"approved"}}
    )
    assert not approval_event_allowed(
        sender="johanannunez", **{**args, "issue_labels": base | {"sent"}}
    )
    assert not approval_event_allowed(sender="johanannunez", already_sent=True, **args)


def test_calendar_writes_are_limited_to_existing_owned_primary_calendar_events():
    action = {
        "type": "calendar_set_busy",
        "account": "personal",
        "calendar_id": "primary",
        "event_id": "event-1",
    }
    good = {
        "sources": {
            "google_calendar": {
                "personal": {
                    "primary_calendar_id": "primary",
                    "events": [{"id": "event-1", "calendar_id": "primary", "owned_by_user": True}],
                }
            }
        }
    }
    actions = parse_actions([action, {"type": "notify", "text": "test"}], "morning-briefing")
    assert validate_action_context(actions, good) == []
    shared = {
        "sources": {
            "google_calendar": {
                "personal": {
                    "primary_calendar_id": "primary",
                    "events": [{"id": "event-1", "calendar_id": "shared", "owned_by_user": False}],
                }
            }
        }
    }
    assert validate_action_context(actions, shared)
    with pytest.raises(ValueError, match="source data is required"):
        validate_run("morning-briefing", [action, {"type": "notify", "text": "test"}], {})


def test_calendar_blocks_require_primary_calendar_sb_title_and_valid_timestamps():
    action = {
        "type": "calendar_block",
        "account": "personal",
        "calendar_id": "primary",
        "title": "SB: Focus",
        "start": "2026-10-26T09:00:00-05:00",
        "end": "2026-10-26T10:00:00-05:00",
    }
    source = {"sources": {"google_calendar": {"personal": {"primary_calendar_id": "primary"}}}}
    actions = parse_actions([action, {"type": "notify", "text": "test"}], "morning-briefing")
    assert validate_action_context(actions, source) == []
    invalid = {**action, "title": "Focus"}
    with pytest.raises(ValidationError):
        parse_actions([invalid], "morning-briefing")


def test_todoist_completion_requires_task_and_source_evidence_from_this_run():
    action = {
        "type": "todoist_complete",
        "task_id": "task-1",
        "proof_source": "google_calendar",
        "proof_detail": "Meeting completed in this run",
    }
    source = {
        "sources": {
            "todoist": {"open_tasks": [{"id": "task-1"}]},
            "google_calendar": {"events": [{"id": "event-1"}]},
        }
    }
    actions = parse_actions([action, {"type": "notify", "text": "test"}], "morning-briefing")
    assert validate_action_context(actions, source) == []
    assert validate_action_context(actions, {"sources": {}})


def test_todoist_completion_proof_is_retained_in_apply_summary():
    actions = [
        {
            "type": "todoist_complete",
            "task_id": "task-1",
            "proof_source": "google_calendar",
            "proof_detail": "Meeting completed in this run",
        },
        {"type": "notify", "text": "Fixture summary"},
    ]
    source_data = {
        "sources": {
            "todoist": {"open_tasks": [{"id": "task-1"}]},
            "google_calendar": {"events": [{"id": "event-1"}]},
        }
    }
    plan = validate_run("morning-briefing", actions, {}, source_data=source_data)
    summary = execute_actions(
        plan,
        {"todoist_complete": lambda action: None, "notify": lambda action: None},
    )
    assert summary[0]["proof"] == "google_calendar: Meeting completed in this run"


@pytest.mark.parametrize(
    "worker", ["morning-briefing", "evening-check-in", "weekly-review", "monthly-close"]
)
def test_required_notify_action_is_exactly_once(worker):
    with pytest.raises(ValueError, match="exactly one"):
        parse_actions([], worker)
    with pytest.raises(ValueError, match="exactly one"):
        parse_actions(
            [{"type": "notify", "text": "one"}, {"type": "notify", "text": "two"}], worker
        )
