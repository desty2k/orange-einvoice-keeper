from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from types import SimpleNamespace

from orange_einvoice.config import AccountSettings, Settings
from orange_einvoice.models import AccountState, AccountStatus, LoginResult, LoginStatus
from orange_einvoice.runner import Runner


class FakeRepository:
    def __init__(self) -> None:
        self.updates: list[tuple[AccountState, str, str | None]] = []

    def update(self, state: AccountState, event: str, detail: str | None) -> None:
        self.updates.append((state, event, detail))


class FakeBrowser:
    def __init__(self) -> None:
        self.page = object()
        self.sessions = 0

    @asynccontextmanager
    async def session(self, account: AccountSettings):
        self.sessions += 1
        yield SimpleNamespace(page=self.page)


class FakeOrange:
    def __init__(self) -> None:
        self.ensure_pages: list[object] = []
        self.submit_pages: list[object] = []
        self.codes: list[str | None] = []

    async def ensure_login(self, page: object, account: AccountSettings) -> LoginResult:
        self.ensure_pages.append(page)
        return LoginResult(LoginStatus.OTP_REQUIRED)

    async def submit_otp(self, page: object, otp: str | None) -> LoginResult:
        self.submit_pages.append(page)
        self.codes.append(otp)
        return LoginResult(LoginStatus.SUCCESS, next_required_login=date(2026, 10, 8))


class FakeNotifier:
    async def notify(self, event: object) -> None:
        raise AssertionError("success must not notify")


def state() -> AccountState:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    return AccountState("home", AccountStatus.NEW, None, None, None, now, 0, None, now)


async def test_interactive_bootstrap_submits_otp_on_same_live_page(tmp_path: object) -> None:
    account = AccountSettings(name="home", email="home@example.com", password="secret")
    settings = Settings(accounts=[account], data_dir=tmp_path)  # type: ignore[arg-type]
    repository = FakeRepository()
    browser = FakeBrowser()
    orange = FakeOrange()
    runner = Runner(settings, repository, browser, orange, FakeNotifier())  # type: ignore[arg-type]

    result = await runner.bootstrap(account, state(), prompt_otp=lambda: "123456")

    assert result.status is AccountStatus.SUCCESS
    assert browser.sessions == 1
    assert orange.ensure_pages == [browser.page]
    assert orange.submit_pages == [browser.page]
    assert orange.codes == ["123456"]
    assert len(repository.updates) == 1
