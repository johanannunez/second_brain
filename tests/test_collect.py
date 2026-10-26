import json
import os
from datetime import UTC, datetime

from sb.collect import CollectorError, collect_run, write_data_file


class GoodCollector:
    name = "mail"

    def collect(self):
        return {"messages": [{"body": "Door code: 3344"}]}


class FailedCollector:
    name = "calendar"

    def collect(self):
        raise CollectorError("calendar", "source unavailable", status_code=503)


def test_collection_isolates_failures_and_redacts_before_returning_data():
    output = collect_run(
        [GoodCollector(), FailedCollector()],
        now=datetime(2026, 10, 26, 16, tzinfo=UTC),
    )
    assert output["sources"]["mail"]["messages"][0]["body"] == "Door code: [REDACTED]"
    assert output["run"]["source_failures"] == {"calendar": "source unavailable (HTTP 503)"}
    assert "door_code_included" in output["redaction_flags"]
    assert output["run"]["now_central"].endswith("-05:00")
    assert output["run"]["now_pacific"].endswith("-07:00")


def test_unexpected_exception_text_is_not_exposed_in_source_failure():
    class LeakingCollector:
        name = "provider"

        def collect(self):
            raise RuntimeError("Bearer super-secret")

    output = collect_run([LeakingCollector()])
    assert output["run"]["source_failures"]["provider"] == "source unavailable (RuntimeError)"
    assert "super-secret" not in str(output)


def test_explicit_source_errors_are_sanitized_before_entering_run_metadata():
    class SensitiveFailure:
        name = "mail"

        def collect(self):
            raise CollectorError("mail", "failed with token: fake-secret")

    output = collect_run([SensitiveFailure()])
    assert output["run"]["source_failures"]["mail"] == "provider error details redacted"
    assert "fake-secret" not in str(output)


def test_data_file_is_redacted_atomic_and_private(tmp_path):
    target = tmp_path / "data.json"
    write_data_file(target, {"message": "Door code: 1212"})
    assert json.loads(target.read_text()) == {"message": "Door code: [REDACTED]"}
    assert os.stat(target).st_mode & 0o777 == 0o600
