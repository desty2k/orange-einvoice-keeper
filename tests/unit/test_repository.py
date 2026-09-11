from datetime import UTC, datetime

from orange_einvoice.config import AccountSettings
from orange_einvoice.models import AccountStatus
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
