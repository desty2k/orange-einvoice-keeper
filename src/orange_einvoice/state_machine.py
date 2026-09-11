from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from orange_einvoice.config import Settings
from orange_einvoice.models import AccountState, AccountStatus, LoginResult, LoginStatus


def transition(state: AccountState, result: LoginResult, settings: Settings, now: datetime) -> AccountState:
    """Convert an Orange-domain outcome into durable scheduling state."""
    if result.status is LoginStatus.SUCCESS:
        scheduled = schedule_for_deadline(result.next_required_login, state.account_name, settings, now)
        return AccountState(state.account_name, AccountStatus.SUCCESS, now, now, result.next_required_login,
                            scheduled, 0, None, now)
    failures = state.consecutive_failures + 1
    if result.status is LoginStatus.OTP_REQUIRED:
        return AccountState(state.account_name, AccountStatus.OTP_REQUIRED, now, state.last_success_at,
                            state.next_required_login, now + timedelta(hours=settings.otp_retry_delay_hours),
                            failures, result.detail or "OTP required", now)
    if result.status is LoginStatus.INVALID_CREDENTIALS:
        return AccountState(state.account_name, AccountStatus.INVALID_CREDENTIALS, now, state.last_success_at,
                            state.next_required_login,
                            now + timedelta(hours=settings.invalid_credentials_retry_delay_hours), failures,
                            result.detail or "invalid credentials", now)
    retry_hours = min(settings.retry_delay_hours * (2 ** min(failures - 1, 2)), 24)
    return AccountState(state.account_name, AccountStatus.RETRY, now, state.last_success_at,
                        state.next_required_login, now + timedelta(hours=retry_hours), failures,
                        result.detail or "temporary Orange failure", now)


def schedule_for_deadline(deadline: date | None, account_name: str, settings: Settings, now: datetime) -> datetime:
    """Compute deterministic local-window schedule, falling back to normal retry for unknown dates."""
    if deadline is None:
        return now + timedelta(hours=settings.retry_delay_hours)
    zone = ZoneInfo(settings.timezone)
    target = deadline - timedelta(days=settings.login_advance_days)
    seed = hashlib.sha256(account_name.encode()).digest()
    offset_minutes = int.from_bytes(seed[:4], "big") % (settings.schedule_window_hours * 60)
    local = datetime.combine(target, time(settings.schedule_window_start_hour), tzinfo=zone)
    scheduled = local + timedelta(minutes=offset_minutes)
    return max(scheduled.astimezone(UTC), now + timedelta(minutes=1))
