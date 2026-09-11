from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from orange_einvoice.config import AccountSettings, Settings
from orange_einvoice.models import AccountState, AccountStatus, LoginResult, LoginStatus
from orange_einvoice.state_machine import schedule_for_deadline, transition


def make_settings() -> Settings:
    return Settings(accounts=[AccountSettings(name="home", email="home@example.com", password="secret")])


def make_state() -> AccountState:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    return AccountState("home", AccountStatus.NEW, None, None, None, now, 0, None, now)


def test_accounts_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="unique"):
        Settings(accounts=[AccountSettings(name="home", email="a@example.com", password="x"), AccountSettings(name="home", email="b@example.com", password="x")])


def test_success_schedules_seven_days_before_deadline_in_deterministic_window() -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    scheduled = schedule_for_deadline(date(2026, 10, 8), "home", make_settings(), now)
    local = scheduled.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Warsaw"))
    assert local.date() == date(2026, 10, 1)
    assert 3 <= local.hour < 6
    assert scheduled == schedule_for_deadline(date(2026, 10, 8), "home", make_settings(), now)


def test_otp_transition_is_deliberately_slow() -> None:
    settings, now = make_settings(), datetime(2026, 9, 1, tzinfo=UTC)
    state = transition(make_state(), LoginResult(LoginStatus.OTP_REQUIRED), settings, now)
    assert state.status is AccountStatus.OTP_REQUIRED
    assert state.next_attempt_at == now + timedelta(hours=24)


def test_temporary_errors_backoff_and_cap() -> None:
    settings, now = make_settings(), datetime(2026, 9, 1, tzinfo=UTC)
    first = transition(make_state(), LoginResult(LoginStatus.TEMPORARY_FAILURE), settings, now)
    second = transition(first, LoginResult(LoginStatus.TEMPORARY_FAILURE), settings, now)
    fourth = transition(second, LoginResult(LoginStatus.TEMPORARY_FAILURE), settings, now)
    assert first.next_attempt_at == now + timedelta(hours=6)
    assert second.next_attempt_at == now + timedelta(hours=12)
    assert fourth.next_attempt_at == now + timedelta(hours=24)


def test_success_without_orange_deadline_uses_monthly_fallback_not_retry_delay() -> None:
    settings = make_settings()
    now = datetime(2026, 9, 1, tzinfo=UTC)
    result = transition(make_state(), LoginResult(LoginStatus.SUCCESS), settings, now)
    assert result.status is AccountStatus.SUCCESS
    assert result.next_attempt_at == now + timedelta(days=25)
