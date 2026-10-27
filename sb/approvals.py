"""Fail-closed validation for outbox approval events.

This module decides whether a GitHub issue event is eligible for a send attempt.
It does not send messages or mutate GitHub/provider state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApprovalDecision:
    eligible: bool
    reason: str
    issue_number: int | None = None


def validate_approval_event(
    event: Mapping[str, Any],
    *,
    authorized_login: str = "johanannunez",
    claimed: bool = False,
) -> ApprovalDecision:
    """Allow only a human owner adding `approved` to an open outbox issue.

    Listening only to the `labeled` action means an issue created with the
    `approved` label is ignored: its creation event is `opened`, not `labeled`.
    A durable send claim must be recorded before provider I/O; repeats then fail
    closed. Provider-side idempotency is still required for exactly-once delivery.
    """
    if event.get("action") != "labeled":
        return ApprovalDecision(False, "event is not an approval label transition")

    sender = event.get("sender")
    if not isinstance(sender, Mapping) or sender.get("login") != authorized_login:
        return ApprovalDecision(False, "label was not added by the authorized user")

    label = event.get("label")
    if not isinstance(label, Mapping) or label.get("name") != "approved":
        return ApprovalDecision(False, "changed label is not approved")

    issue = event.get("issue")
    if not isinstance(issue, Mapping):
        return ApprovalDecision(False, "issue payload is missing")
    if "pull_request" in issue:
        return ApprovalDecision(False, "pull requests are not outbox items")
    if issue.get("state") != "open":
        return ApprovalDecision(False, "outbox issue is not open")
    labels = issue.get("labels")
    names = (
        {
            label_item.get("name")
            for label_item in labels
            if isinstance(label_item, Mapping)
        }
        if isinstance(labels, list)
        else set()
    )
    if not {"outbox", "approved"}.issubset(names):
        return ApprovalDecision(False, "issue must have both outbox and approved labels")

    number = issue.get("number")
    if not isinstance(number, int) or number < 1:
        return ApprovalDecision(False, "issue number is invalid")
    if claimed:
        return ApprovalDecision(False, "a send attempt was already claimed", number)
    return ApprovalDecision(True, "authorized owner approved an open outbox item", number)
