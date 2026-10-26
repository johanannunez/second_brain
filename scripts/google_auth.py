#!/usr/bin/env python3
"""Mint a Google OAuth refresh token and save it outside the repository."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", choices=("parcel", "personal"), required=True)
    parser.add_argument("--client-secrets", type=Path, required=True)
    args = parser.parse_args()

    if not args.client_secrets.is_file():
        parser.error("--client-secrets must point to the downloaded OAuth client JSON")

    output_dir = Path.home() / ".config" / "second-brain"
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_path = output_dir / f"google-refresh-token-{args.account}.json"
    if output_path.exists() or output_path.is_symlink():
        raise SystemExit(f"Refusing to overwrite the existing token file: {output_path}")

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not credentials.refresh_token:
        raise SystemExit(
            "Google returned no refresh token. Revoke this app's existing account grant "
            "and run the helper again to request consent."
        )

    payload = {
        "account": args.account,
        "refresh_token": credentials.refresh_token,
        "scopes": SCOPES,
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_dir,
            prefix=f".{output_path.name}.",
            delete=False,
        ) as output_file:
            temp_path = Path(output_file.name)
            json.dump(payload, output_file, indent=2)
            output_file.write("\n")
            output_file.flush()
            os.fsync(output_file.fileno())
        os.link(temp_path, output_path)
    except FileExistsError as exc:
        raise SystemExit(
            f"Refusing to overwrite the existing token file: {output_path}"
        ) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    print(f"Saved the {args.account} refresh token to {output_path} (permissions 0600).")
    print("Copy it to the matching GitHub Actions secret using a secure local method.")


if __name__ == "__main__":
    main()
