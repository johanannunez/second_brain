import pytest

from sb.clients.hospitable import HospitableThreadReads
from sb.clients.http import APIError


def test_hospitable_thread_policy_waits_30_seconds_then_retries_once_on_429():
    calls = []
    delays = []

    def fetch():
        calls.append(1)
        if len(calls) == 1:
            raise APIError("rate limited", status_code=429)
        return {"messages": [{"id": "fake-message"}]}

    reader = HospitableThreadReads(sleep=delays.append)
    result = reader.fetch_once_per_run("reservation-id", fetch)
    assert result.reviewed is True
    assert result.payload == {"messages": [{"id": "fake-message"}]}
    assert calls == [1, 1]
    assert delays == [30]


def test_hospitable_marks_thread_not_reviewed_after_second_429_and_fetches_once_per_run():
    calls = []
    delays = []

    def fetch():
        calls.append(1)
        raise APIError("rate limited", status_code=429)

    reader = HospitableThreadReads(sleep=delays.append)
    first = reader.fetch_once_per_run("reservation-id", fetch)
    second = reader.fetch_once_per_run("reservation-id", fetch)
    assert first.reviewed is False
    assert first.note == "not reviewed after rate limit; retry once next run"
    assert second == first
    assert len(calls) == 2
    assert delays == [30]


def test_hospitable_does_not_retry_non_rate_limit_errors():
    calls = []
    reader = HospitableThreadReads(sleep=lambda _: None)

    def fetch():
        calls.append(1)
        raise APIError("forbidden", status_code=403)

    with pytest.raises(APIError):
        reader.fetch_once_per_run("reservation-id", fetch)
    assert len(calls) == 1
