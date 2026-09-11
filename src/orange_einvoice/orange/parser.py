from __future__ import annotations

import re
from datetime import date

from orange_einvoice.models import LoginStatus
from orange_einvoice.orange.selectors import (
    DASHBOARD_MARKERS,
    INVALID_CREDENTIAL_MARKERS,
    NEXT_LOGIN_MARKERS,
    OTP_MARKERS,
)

_DATE_PATTERN = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")


def classify_page(text: str) -> LoginStatus:
    normalized = text.casefold()
    if any(marker in normalized for marker in OTP_MARKERS):
        return LoginStatus.OTP_REQUIRED
    if any(marker in normalized for marker in INVALID_CREDENTIAL_MARKERS):
        return LoginStatus.INVALID_CREDENTIALS
    if any(marker in normalized for marker in DASHBOARD_MARKERS):
        return LoginStatus.SUCCESS
    return LoginStatus.UNEXPECTED_PAGE


def parse_next_required_login(text: str) -> date | None:
    normalized = text.casefold()
    marker_positions = [normalized.find(marker) for marker in NEXT_LOGIN_MARKERS if marker in normalized]
    if not marker_positions:
        return None
    snippet = text[min(marker_positions): min(marker_positions) + 500]
    match = _DATE_PATTERN.search(snippet)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None
