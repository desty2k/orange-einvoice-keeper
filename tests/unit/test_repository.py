from datetime import UTC, datetime, timedelta

from orange_einvoice.config import AccountSettings
from orange_einvoice.models import AccountState, AccountStatus
from orange_einvoice.state import SQLiteStateRepository


def test_reconcile_creates_due_account_and_disables_removed_account(tmp_path: object) -> None:
    path = tmp_path / "state.db"  # type: ignore[operator]
    repository = SQLiteStateRepository(path)
    now = datetime(2026, 9, 1, tzinfo=UTC)
    repository.open()
    try:
        home = AccountSettings(name="home", email="home@example.com", password="secret")
        repository.reconcile([home], now)
        state = repository.get("home")
        assert state is not None
        assert state.status is AccountStatus.NEW
        assert repository.due_accounts(now)[0].account_name == "home"
        repository.reconcile([], now)
        assert repository.get("home").status is AccountStatus.DISABLED  # type: ignore[union-attr]
    finally:
        repository.close()


def test_cap_success_schedules_moves_late_success_forward_to_weekly(tmp_path: object) -> None:
    path = tmp_path / "state.db"  # type: ignore[operator]
    repository = SQLiteStateRepository(path)
    now = datetime(2026, 9, 11, tzinfo=UTC)
    repository.open()
    try:
        home = AccountSettings(name="home", email="home@example.com", password="secret")
        repository.reconcile([home], now)
        repository.update(
            AccountState(
                "home",
                AccountStatus.SUCCESS,
                now,
                now,
                None,
                now + timedelta(days=25),
                0,
                None,
                now,
            ),
            "LOGIN_SUCCESS",
        )

        repository.cap_success_schedules(interval_days=7, now=now)

        state = repository.get("home")
        assert state is not None
        assert state.next_attempt_at == now + timedelta(days=7)
    finally:
        repository.close()
