from __future__ import annotations

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from orange_einvoice.config import AccountSettings, Settings
from orange_einvoice.models import LoginResult, LoginStatus
from orange_einvoice.orange.client import OrangeClient


class FakePage:
    def __init__(self) -> None:
        self.waits: list[int] = []

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


class SequencedClient(OrangeClient):
    def __init__(self, results: list[LoginResult | Exception]) -> None:
        settings = Settings(
            accounts=[AccountSettings(name="home", email="home@example.com", password="secret")],
            browser_timeout_ms=1_000,
        )
        super().__init__(settings)
        self.results = iter(results)

    async def _approve_trusted_device(self, page: FakePage) -> bool:
        return False

    async def _classify(
        self, page: FakePage, *, timeout_ms: int | None = None
    ) -> LoginResult:
        item = next(self.results)
        if isinstance(item, Exception):
            raise item
        return item


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


async def test_otp_transition_retries_short_dom_read_timeout_before_success() -> None:
    client = SequencedClient(
        [
            PlaywrightTimeoutError("body not ready"),
            LoginResult(LoginStatus.SUCCESS),
        ]
    )
    page = FakePage()

    result = await client._wait_for_otp_resolution(page)  # noqa: SLF001

    assert result.status is LoginStatus.SUCCESS
    assert page.waits == [250]


class TrustedDeviceClient(SequencedClient):
    def __init__(self, results: list[LoginResult | Exception]) -> None:
        super().__init__(results)
        self.trusted_device_checks = 0

    async def _approve_trusted_device(self, page: FakePage) -> bool:
        self.trusted_device_checks += 1
        return self.trusted_device_checks == 1


async def test_otp_transition_selects_trusted_device_before_success() -> None:
    client = TrustedDeviceClient([LoginResult(LoginStatus.SUCCESS)])
    page = FakePage()

    result = await client._wait_for_otp_resolution(page)  # noqa: SLF001

    assert result.status is LoginStatus.SUCCESS
    assert client.trusted_device_checks == 1
    assert page.waits == [250]


async def test_password_transition_selects_trusted_device_before_success() -> None:
    client = TrustedDeviceClient([LoginResult(LoginStatus.SUCCESS)])
    page = FakePage()

    result = await client._wait_for_login_resolution(page)  # noqa: SLF001

    assert result.status is LoginStatus.SUCCESS
    assert client.trusted_device_checks == 1
    assert page.waits == [250]


async def test_password_transition_retries_generic_navigation_error_before_success() -> None:
    client = SequencedClient(
        [
            PlaywrightError("execution context was destroyed"),
            LoginResult(LoginStatus.SUCCESS),
        ]
    )
    page = FakePage()

    result = await client._wait_for_login_resolution(page)  # noqa: SLF001

    assert result.status is LoginStatus.SUCCESS
    assert page.waits == [250]
