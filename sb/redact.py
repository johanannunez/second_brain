"""Redact credentials and sensitive identifiers before data leaves collection."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_CODE_KEYS = re.compile(
    r"(?:door|lockbox|smart.?lock).*code|code.*(?:door|lockbox|smart.?lock)", re.I
)
_WIFI_KEYS = re.compile(
    r"(?:wifi|wi-fi).*(?:password|passphrase|key)|(?:password|passphrase).*(?:wifi|wi-fi)", re.I
)
_SECRET_KEYS = re.compile(
    r"(?:^|_)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|client_secret)(?:$|_)",
    re.I,
)
_ACCOUNT_KEYS = re.compile(
    r"(?:(?:card|account|routing|bank).*(?:number|no)|(?:^|_)(?:ssn|ein|tax.?id)(?:$|_))",
    re.I,
)
_PRIVATE_ID_KEYS = re.compile(
    r"(?:guest|resident).*(?:id|address)|(?:passport|government.?id)", re.I
)
_PRIVATE_AMOUNT_KEYS = re.compile(
    r"(?:tenant.*(?:rent|payment|amount)|personal.*income|account.*balance|balance.*account)", re.I
)
_HEALTH_TERMS = re.compile(
    r"\b(?:medical|health|diagnosis|medication|prescription|therapy|symptom|hospitalized)\b",
    re.I,
)
_RESIDENT_CONTEXT = re.compile(
    r"\bJadwin Recovery\b.{0,80}\bresident\b|\bresident\b.{0,80}\bJadwin Recovery\b", re.I
)
_CODE_TEXT = re.compile(
    r"(?P<label>(?:door|lockbox|smart[ -]?lock)(?:[ -]?(?:entry|access))?[ -]?code)"
    r"(?P<sep>\s*(?:is|:|=)\s*)(?P<value>[^\s,;.!]+)",
    re.I,
)
_WIFI_TEXT = re.compile(
    r"(?P<label>(?:wi[ -]?fi|wireless)(?:[ -]?(?:password|passphrase|key))?)"
    r"(?P<sep>\s*(?:password|passphrase|key)?\s*(?:is|:|=)\s*)"
    r"(?P<value>[^\s,;.!]+)",
    re.I,
)
_TOKEN_TEXT = re.compile(
    r"(?P<label>(?:api[ _-]?)?(?:access[ _-]?|refresh[ _-]?)?token|api[ _-]?key|"
    r"password|client[ _-]?secret)\s*(?P<sep>[:=]|\bis\b)\s*(?P<value>[^\s,;]+)",
    re.I,
)
_FINANCIAL_TEXT = re.compile(
    r"(?P<label>\b(?:credit[ -]?card|debit[ -]?card|card|bank[ -]?account|account|"
    r"routing|ssn|ein|tax[ -]?id)(?:[ -]?(?:number|no\.?))?)"
    r"\s*(?:is|:|=)\s*(?P<value>\d[\d -]{4,28}\d)",
    re.I,
)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I)
_LONG_DIGITS = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[ .()-]*){9,15}(?!\w)")


def _luhn(number: str) -> bool:
    digits = [int(char) for char in number if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _redact_string(value: str, flags: set[str]) -> str:
    if _HEALTH_TERMS.search(value):
        flags.add("health_information_included")
        return REDACTED
    if _RESIDENT_CONTEXT.search(value):
        flags.add("resident_information_included")
        return REDACTED

    def replace_code(match: re.Match[str]) -> str:
        label = match.group("label").lower().replace(" ", "_").replace("-", "_")
        if "lockbox" in label:
            flags.add("lockbox_code_included")
        elif "smart" in label:
            flags.add("smart_lock_code_included")
        else:
            flags.add("door_code_included")
        return f"{match.group('label')}{match.group('sep')}{REDACTED}"

    value = _CODE_TEXT.sub(replace_code, value)

    def replace_wifi(match: re.Match[str]) -> str:
        flags.add("wifi_password_included")
        return f"{match.group('label')}{match.group('sep')}{REDACTED}"

    value = _WIFI_TEXT.sub(replace_wifi, value)

    def replace_token(match: re.Match[str]) -> str:
        flags.add("token_included")
        return f"{match.group('label')}{match.group('sep')}{REDACTED}"

    value = _TOKEN_TEXT.sub(replace_token, value)
    if _BEARER.search(value):
        flags.add("token_included")
        value = _BEARER.sub(f"Bearer {REDACTED}", value)

    def replace_financial(match: re.Match[str]) -> str:
        label = match.group("label").lower()
        flags.add("card_number_included" if "card" in label else "financial_identifier_included")
        return f"{match.group('label')}: {REDACTED}"

    value = _FINANCIAL_TEXT.sub(replace_financial, value)

    def replace_digits(match: re.Match[str]) -> str:
        if _luhn(match.group(0)):
            flags.add("card_number_included")
            return REDACTED
        return match.group(0)

    value = _LONG_DIGITS.sub(replace_digits, value)
    if _EMAIL.search(value):
        flags.add("contact_detail_included")
        value = _EMAIL.sub(REDACTED, value)
    if _PHONE.search(value):
        flags.add("contact_detail_included")
        value = _PHONE.sub(REDACTED, value)
    return value


def redact(value: Any) -> tuple[Any, list[str]]:
    """Return a redacted deep copy and sorted flags describing content removed."""
    flags: set[str] = set()

    def visit(item: Any, key: str = "") -> Any:
        if _CODE_KEYS.search(key):
            if "lockbox" in key.lower():
                flags.add("lockbox_code_included")
            elif "smart" in key.lower():
                flags.add("smart_lock_code_included")
            else:
                flags.add("door_code_included")
            return REDACTED
        if _WIFI_KEYS.search(key):
            flags.add("wifi_password_included")
            return REDACTED
        if _SECRET_KEYS.search(key):
            flags.add(
                "token_included"
                if "token" in key.lower() or "key" in key.lower()
                else "secret_included"
            )
            return REDACTED
        if _ACCOUNT_KEYS.search(key):
            flags.add("financial_identifier_included")
            return REDACTED
        if _PRIVATE_ID_KEYS.search(key):
            flags.add("contact_detail_included")
            return REDACTED
        if _PRIVATE_AMOUNT_KEYS.search(key):
            flags.add("financial_identifier_included")
            return REDACTED
        if isinstance(item, str):
            return _redact_string(item, flags)
        if isinstance(item, Mapping):
            return {
                str(child_key): visit(child_value, str(child_key))
                for child_key, child_value in item.items()
            }
        if isinstance(item, tuple):
            return [visit(child) for child in item]
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            return [visit(child) for child in item]
        return item

    return visit(value), sorted(flags)
