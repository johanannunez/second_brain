from sb.approvals import validate_approval_event


def event(**updates):
    result = {
        "action": "labeled",
        "sender": {"login": "johanannunez"},
        "label": {"name": "approved"},
        "issue": {
            "number": 42,
            "state": "open",
            "labels": [{"name": "outbox"}, {"name": "approved"}],
        },
    }
    result.update(updates)
    return result


def test_owner_labeling_open_outbox_item_is_eligible():
    decision = validate_approval_event(event())
    assert decision.eligible
    assert decision.issue_number == 42


def test_other_sender_is_rejected():
    decision = validate_approval_event(event(sender={"login": "someone-else"}))
    assert not decision.eligible
    assert "authorized user" in decision.reason


def test_created_with_approved_label_is_not_a_label_transition():
    decision = validate_approval_event(event(action="opened"))
    assert not decision.eligible


def test_missing_outbox_label_is_rejected():
    decision = validate_approval_event(
        event(issue={"number": 42, "state": "open", "labels": [{"name": "approved"}]})
    )
    assert not decision.eligible


def test_closed_item_and_pull_requests_are_rejected():
    assert not validate_approval_event(
        event(issue={"number": 42, "state": "closed", "labels": []})
    ).eligible
    assert not validate_approval_event(
        event(issue={"number": 42, "state": "open", "labels": [], "pull_request": {}})
    ).eligible


def test_repeat_claim_is_rejected():
    decision = validate_approval_event(event(), claimed=True)
    assert not decision.eligible
    assert decision.issue_number == 42
    assert "already claimed" in decision.reason
