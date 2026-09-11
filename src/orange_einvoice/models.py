from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class AccountStatus(StrEnum):
    NEW = "new"
    READY = "ready"
    SUCCESS = "success"
    RETRY = "retry"
    OTP_REQUIRED = "otp_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    DISABLED = "disabled"


class LoginStatus(StrEnum):
    SUCCESS = "success"
    OTP_REQUIRED = "otp_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    UNEXPECTED_PAGE = "unexpected_page"
    TEMPORARY_FAILURE = "temporary_failure"


@dataclass(frozen=True, slots=True)
class LoginResult:
    status: LoginStatus
    next_required_login: date | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class AccountState:
    account_name: str
    status: AccountStatus
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    next_required_login: date | None
    next_attempt_at: datetime | None
    consecutive_failures: int
    last_error: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationEvent:
    event_type: str
    account_name: str
    detail: str | None = None
