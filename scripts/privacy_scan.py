"""Scan repository text for common high-risk private values.

This is a guardrail, not a substitute for reviewing source content. Test fixtures
are excluded because they intentionally contain fake sensitive values.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EMAILS = {"hello@theparcelco.com", "jo@johanannunez.com"}
ALLOWED_PHONES = {"6058007033"}
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)")
TOKEN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9]{24,})\b"
)
LABELED_SECRET = re.compile(
    r"(?i)\b(?:door|lockbox|smart[- ]?lock)\s+code\s*[:=]\s*\S+|"
    r"\bwi[- ]?fi\s+password\s*[:=]\s*\S+|"
    r"\b(?:api\s+key|access\s+token|refresh\s+token)\s*[:=]\s*\S+|"
    r"\b(?:SSN|social security number|EIN|tax ID|bank account|account number)"
    r"\s*(?:is|[:=])?\s*\d[\d -]{5,20}\b"
)
JADWIN_RESIDENT = re.compile(
    r"(?is)Jadwin Recovery.{0,100}\bresidents?\b|\bresidents?\b.{0,100}Jadwin Recovery"
)


def _luhn(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def scan_text(text: str) -> list[str]:
    findings: list[str] = []
    if TOKEN.search(text):
        findings.append("credential-like token")
    if LABELED_SECRET.search(text):
        findings.append("labeled access code or secret")
    if JADWIN_RESIDENT.search(text):
        findings.append("Jadwin Recovery resident reference")
    if any(email.lower() not in ALLOWED_EMAILS for email in EMAIL.findall(text)):
        findings.append("non-allowlisted email address")
    if any(
        "".join(char for char in match if char.isdigit()) not in ALLOWED_PHONES
        for match in PHONE.findall(text)
    ):
        findings.append("phone number")
    if any(_luhn(match.group()) for match in re.finditer(r"(?:\d[ -]?){13,19}", text)):
        findings.append("payment-card number")
    return findings


def scan_repo(root: Path = ROOT) -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    ).stdout.split(b"\0")
    failures: list[str] = []
    for raw_path in tracked:
        if not raw_path:
            continue
        path = Path(raw_path.decode())
        if (
            path.parts[0] in {"tests", "docs"}
            or path.name in {"AGENTS.md", "CLAUDE.md"}
            or path.suffix not in {".md", ".json"}
        ):
            continue
        content = (root / path).read_text(encoding="utf-8")
        for finding in scan_text(content):
            failures.append(f"{path}: {finding}")
    return failures


if __name__ == "__main__":
    problems = scan_repo()
    if problems:
        print("Privacy scan found possible sensitive values:", file=sys.stderr)
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    print("Privacy scan passed.")
