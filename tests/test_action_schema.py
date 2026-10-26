import json
from pathlib import Path

from sb.actions import ACTION_LIST_ADAPTER


def test_checked_in_action_schema_matches_runtime_schema():
    stored = json.loads(Path("schemas/actions.schema.json").read_text())
    assert stored == ACTION_LIST_ADAPTER.json_schema()
