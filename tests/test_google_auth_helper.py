import importlib
import json
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_oauth_helper_saves_fake_token_mode_0600_and_refuses_to_overwrite(tmp_path, monkeypatch):
    calls = []

    class FakeFlow:
        def run_local_server(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(refresh_token="fake-refresh-token")

    flow_module = types.ModuleType("google_auth_oauthlib.flow")
    flow_module.InstalledAppFlow = type(
        "InstalledAppFlow",
        (),
        {"from_client_secrets_file": staticmethod(lambda *_: FakeFlow())},
    )
    package_module = types.ModuleType("google_auth_oauthlib")
    package_module.flow = flow_module
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib", package_module)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", flow_module)

    script = importlib.util.spec_from_file_location(
        "second_brain_google_auth", Path("scripts/google_auth.py")
    )
    module = importlib.util.module_from_spec(script)
    assert script.loader is not None
    script.loader.exec_module(module)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    client_secrets = tmp_path / "client.json"
    client_secrets.write_text("{}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["google_auth.py", "--account", "parcel", "--client-secrets", str(client_secrets)],
    )

    module.main()
    token_file = tmp_path / ".config/second-brain/google-refresh-token-parcel.json"
    original = token_file.read_bytes()
    assert json.loads(original)["refresh_token"] == "fake-refresh-token"
    assert os.stat(token_file).st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        module.main()
    assert len(calls) == 1
    assert token_file.read_bytes() == original
    assert not list(token_file.parent.glob("*.tmp"))
