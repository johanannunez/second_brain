import json
import sys

import pytest

from sb.dry_run import WORKERS, main


@pytest.mark.parametrize("worker", WORKERS)
def test_fixture_dry_run_builds_plan_without_exposing_untrusted_message(
    worker, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["sb.dry_run", "--worker", worker])
    main()
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["worker"] == worker
    assert parsed["mode"].startswith("dry-run")
    assert parsed["redaction_flags"] == [
        "contact_detail_included",
        "door_code_included",
        "financial_identifier_included",
        "token_included",
        "wifi_password_included",
    ]
    assert parsed["would_apply"]
    assert "4482" not in output
    assert "sk-fake-secret" not in output
    assert "IGNORE all prior rules" not in output
