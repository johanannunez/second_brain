"""Typed action payloads and worker-specific capability allowlists."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from sb.redact import redact

type ShortText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
type Identifier = Annotated[str, StringConstraints(min_length=1, max_length=300)]


def _reject_sensitive_content(value: str) -> str:
    safe_value, flags = redact(value)
    if safe_value != value or flags:
        raise ValueError("action content contains a sensitive value")
    return value


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: str


class GmailDraft(Action):
    type: Literal["gmail_draft"]
    account: Literal["parcel", "personal"]
    thread_id: Identifier
    subject: ShortText
    body: ShortText

    @field_validator("subject", "body")
    @classmethod
    def safe_draft_content(cls, value: str) -> str:
        return _reject_sensitive_content(value)


class GmailLabel(Action):
    type: Literal["gmail_label"]
    account: Literal["parcel", "personal"]
    message_id: Identifier
    label: Annotated[str, StringConstraints(min_length=4, max_length=100, pattern=r"^SB/")]


class TodoistCreate(Action):
    type: Literal["todoist_create"]
    content: ShortText
    due_string: Annotated[str, StringConstraints(max_length=200)] | None = None
    description: Annotated[str, StringConstraints(max_length=1000)] = ""
    label: Literal["sb"]

    @field_validator("content", "description")
    @classmethod
    def safe_task_content(cls, value: str) -> str:
        return _reject_sensitive_content(value)


class TodoistComplete(Action):
    type: Literal["todoist_complete"]
    task_id: Identifier
    proof_source: ShortText
    proof_detail: ShortText

    @field_validator("proof_source", "proof_detail")
    @classmethod
    def safe_completion_proof(cls, value: str) -> str:
        return _reject_sensitive_content(value)


class CalendarSetBusy(Action):
    type: Literal["calendar_set_busy"]
    account: Literal["parcel", "personal"]
    calendar_id: Identifier
    event_id: Identifier


class CalendarBlock(Action):
    type: Literal["calendar_block"]
    account: Literal["parcel", "personal"]
    calendar_id: Identifier
    title: Annotated[str, StringConstraints(min_length=4, max_length=300, pattern=r"^SB:")]
    start: ShortText
    end: ShortText

    @field_validator("title")
    @classmethod
    def safe_calendar_title(cls, value: str) -> str:
        return _reject_sensitive_content(value)


class OutboxMessage(Action):
    type: Literal["outbox_message"]
    channel: Literal["quo", "hospitable"]
    recipient_id: Identifier
    message: ShortText
    reason: ShortText

    @field_validator("recipient_id")
    @classmethod
    def recipient_must_be_provider_id(cls, value: str) -> str:
        import re

        if "@" in value or re.fullmatch(r"\+?[0-9(). -]{7,24}", value):
            raise ValueError("outbox recipient must be a provider ID, not contact details")
        return value

    @model_validator(mode="after")
    def message_must_not_contain_sensitive_values(self):
        for field_name in ("message", "reason"):
            safe_value, flags = redact(getattr(self, field_name))
            if safe_value != getattr(self, field_name) or flags:
                raise ValueError("outbox content contains a sensitive value")
        return self


class Notify(Action):
    type: Literal["notify"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=300)]

    @field_validator("text")
    @classmethod
    def message_must_not_contain_sensitive_values(cls, value: str) -> str:
        safe_value, flags = redact(value)
        if safe_value != value or flags:
            raise ValueError("notification contains a sensitive value")
        return value


type ActionItem = Annotated[
    GmailDraft
    | GmailLabel
    | TodoistCreate
    | TodoistComplete
    | CalendarSetBusy
    | CalendarBlock
    | OutboxMessage
    | Notify,
    Field(discriminator="type"),
]

ACTION_ADAPTER = TypeAdapter(ActionItem)
ACTION_LIST_ADAPTER = TypeAdapter(list[ActionItem])

WORKER_ACTIONS: dict[str, frozenset[str]] = {
    "morning-briefing": frozenset(
        {
            "gmail_draft",
            "gmail_label",
            "todoist_create",
            "todoist_complete",
            "calendar_set_busy",
            "calendar_block",
            "outbox_message",
            "notify",
        }
    ),
    "midday-sweep": frozenset(
        {"gmail_draft", "gmail_label", "todoist_create", "outbox_message", "notify"}
    ),
    "evening-check-in": frozenset({"todoist_create", "notify"}),
    "weekly-review": frozenset({"todoist_create", "notify"}),
    "monthly-close": frozenset({"todoist_create", "notify"}),
}

WORKER_PATHS: dict[str, tuple[str, ...]] = {
    "morning-briefing": ("daily/", "dashboard/"),
    "midday-sweep": ("daily/", "dashboard/"),
    "evening-check-in": (
        "daily/",
        "goals/goals.md",
        "businesses/",
        "people/",
        "properties/",
        "profile.md",
        "decisions.md",
    ),
    "weekly-review": ("weekly/", "goals/goals.md"),
    "monthly-close": ("monthly/",),
}

PROTECTED_PATHS = ("AGENTS.md", "CLAUDE.md", "workers/", "sb/", "schemas/", ".github/")


def parse_actions(payload: object, worker: str) -> list[ActionItem]:
    """Validate schema and the named worker's explicit action allowlist."""
    if worker not in WORKER_ACTIONS:
        raise ValueError(f"unknown worker: {worker}")
    actions = ACTION_LIST_ADAPTER.validate_python(payload)
    disallowed = sorted({action.type for action in actions} - WORKER_ACTIONS[worker])
    if disallowed:
        raise ValueError(f"worker {worker} cannot use action type(s): {', '.join(disallowed)}")
    if worker in {"morning-briefing", "evening-check-in", "weekly-review", "monthly-close"}:
        notify_count = sum(action.type == "notify" for action in actions)
        if notify_count != 1:
            raise ValueError(f"worker {worker} must include exactly one notify action")
    if worker == "midday-sweep" and sum(action.type == "notify" for action in actions) > 1:
        raise ValueError("worker midday-sweep may include at most one notify action")
    return actions


def validate_action_context(actions: list[ActionItem], source_data: dict[str, object]) -> list[str]:
    """Require write actions to target objects present in this run's collected data."""
    errors: list[str] = []
    sources = source_data.get("sources")
    if not isinstance(sources, dict):
        if any(
            action.type in {"calendar_set_busy", "calendar_block", "todoist_complete"}
            for action in actions
        ):
            return ["run source data is required to authorize this action"]
        return []

    for action in actions:
        if isinstance(action, CalendarSetBusy):
            account_data = (
                sources.get("google_calendar", {}).get(action.account)
                if isinstance(sources.get("google_calendar"), dict)
                else None
            )
            if not isinstance(account_data, dict):
                errors.append(f"calendar source missing for account {action.account}")
                continue
            primary_id = account_data.get("primary_calendar_id")
            events = account_data.get("events", [])
            event = next(
                (
                    item
                    for item in events
                    if isinstance(item, dict) and item.get("id") == action.event_id
                ),
                None,
            )
            if action.calendar_id != primary_id or not isinstance(event, dict):
                errors.append(
                    "calendar_set_busy must reference an existing event on the primary calendar"
                )
            elif event.get("calendar_id") != primary_id or event.get("owned_by_user") is not True:
                errors.append("calendar_set_busy is limited to Jo's own primary-calendar events")
        elif isinstance(action, CalendarBlock):
            account_data = (
                sources.get("google_calendar", {}).get(action.account)
                if isinstance(sources.get("google_calendar"), dict)
                else None
            )
            if not isinstance(account_data, dict) or action.calendar_id != account_data.get(
                "primary_calendar_id"
            ):
                errors.append("calendar_block is limited to the user's primary calendar")
            else:
                try:
                    from datetime import datetime

                    start = datetime.fromisoformat(action.start.replace("Z", "+00:00"))
                    end = datetime.fromisoformat(action.end.replace("Z", "+00:00"))
                    if start.tzinfo is None or end.tzinfo is None or end <= start:
                        errors.append("calendar_block must have an aware start and a later end")
                except ValueError:
                    errors.append("calendar_block start and end must be ISO datetimes")
        elif isinstance(action, TodoistComplete):
            todoist = sources.get("todoist")
            tasks = todoist.get("open_tasks", []) if isinstance(todoist, dict) else []
            task_exists = any(
                isinstance(item, dict) and str(item.get("id")) == action.task_id for item in tasks
            )
            if action.proof_source not in sources:
                errors.append("todoist_complete proof source is missing from this run")
            if not task_exists:
                errors.append("todoist_complete must reference an open task from this run")
    return errors


def validate_file_changes(worker: str, changes: dict[str, str | None]) -> list[str]:
    """Reject deletions, traversal, protected files, and paths outside worker scope."""
    from pathlib import PurePosixPath

    if worker not in WORKER_PATHS:
        raise ValueError(f"unknown worker: {worker}")
    errors: list[str] = []
    allowed = WORKER_PATHS[worker]
    for raw_path, contents in changes.items():
        path = PurePosixPath(raw_path)
        normalized = path.as_posix()
        if path.is_absolute() or ".." in path.parts or not path.parts:
            errors.append(f"invalid path: {raw_path}")
            continue
        if contents is None:
            errors.append(f"deletions are forbidden: {normalized}")
            continue
        if any(
            normalized == protected.rstrip("/") or normalized.startswith(protected)
            for protected in PROTECTED_PATHS
        ):
            errors.append(f"protected path: {normalized}")
            continue
        if not any(
            normalized.startswith(prefix) if prefix.endswith("/") else normalized == prefix
            for prefix in allowed
        ):
            errors.append(f"path outside {worker} allowlist: {normalized}")
    return errors


def approval_event_allowed(
    *,
    sender: str,
    event_action: str,
    event_label: str,
    issue_labels: set[str],
    already_sent: bool = False,
) -> bool:
    """Allow only Jo adding `approved` to an unsent outbox issue."""
    return (
        sender == "johanannunez"
        and event_action == "labeled"
        and event_label == "approved"
        and "outbox" in issue_labels
        and "expired" not in issue_labels
        and "sent" not in issue_labels
        and not already_sent
    )
