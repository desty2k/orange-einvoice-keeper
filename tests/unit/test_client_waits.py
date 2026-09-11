from __future__ import annotations

from orange_einvoice.config import AccountSettings, Settings
from orange_einvoice.models import LoginResult, LoginStatus
from orange_einvoice.orange.client import OrangeClient


class FakePage:
    def __init__(self) -> None:
        self.waits: list[int] = []

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


class SequencedClient(OrangeClient):
    def __init__(self, results: list[LoginResult]) -> None:
        settings = Settings(
            accounts=[AccountSettings(name="home", email="home@example.com", password="secret")],
            browser_timeout_ms=1_000,
        )
        super().__init__(settings)
        self.results = iter(results)

    async def _classify(self, page: FakePage) -> LoginResult:
        return next(self.results)


async def test_password_transition_waits_for_otp_after_intermediate_pages() -> None:
    client = SequencedClient(
        [
            LoginResult(LoginStatus.UNEXPECTED_PAGE),
            LoginResult(LoginStatus.UNEXPECTED_PAGE),
            LoginResult(LoginStatus.OTP_REQUIRED),
        ]
    )
    page = FakePage()

    result = await client._wait_for_login_resolution(page)  # noqa: SLF001

    assert result.status is LoginStatus.OTP_REQUIRED
    assert page.waits == [250, 250]


async def test_otp_transition_waits_through_intermediate_page_for_success() -> None:
    client = SequencedClient(
        [
            LoginResult(LoginStatus.OTP_REQUIRED),
            LoginResult(LoginStatus.UNEXPECTED_PAGE),
            LoginResult(LoginStatus.SUCCESS),
        ]
    )
    page = FakePage()

    result = await client._wait_for_otp_resolution(page)  # noqa: SLF001

    assert result.status is LoginStatus.SUCCESS
    assert page.waits == [250, 250]
