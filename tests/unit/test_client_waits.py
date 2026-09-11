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


class TextOnlyTrustedButton:
    first: TextOnlyTrustedButton

    def __init__(self) -> None:
        self.first = self
        self.clicked = False

    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    async def click(self) -> None:
        self.clicked = True


class TextOnlyTrustedPage:
    def __init__(self) -> None:
        self.button = TextOnlyTrustedButton()
        self.lookups: list[tuple[str, bool]] = []

    def get_by_text(self, text: str, *, exact: bool) -> TextOnlyTrustedButton:
        self.lookups.append((text, exact))
        return self.button


async def test_trusted_device_uses_exact_visible_text_locator() -> None:
    settings = Settings(
        accounts=[AccountSettings(name="home", email="home@example.com", password="secret")]
    )
    client = OrangeClient(settings)
    page = TextOnlyTrustedPage()

    selected = await client._approve_trusted_device(page)  # noqa: SLF001

    assert selected is True
    assert page.lookups == [("Zaloguj i dodaj do zaufanych", True)]
    assert page.button.clicked is True


class AuthenticatedDashboardPage:
    url = "https://www.orange.pl/moj-orange/uslugi-stacjonarne"


async def test_authenticated_moj_orange_url_is_success_without_dom_read() -> None:
    settings = Settings(
        accounts=[AccountSettings(name="home", email="home@example.com", password="secret")]
    )
    client = OrangeClient(settings)

    result = await client._classify(AuthenticatedDashboardPage())  # type: ignore[arg-type]  # noqa: SLF001

    assert result.status is LoginStatus.SUCCESS


class AuthenticatedDashboardRootPage:
    url = "https://www.orange.pl/moj-orange"


async def test_authenticated_moj_orange_root_url_is_success_without_dom_read() -> None:
    settings = Settings(
        accounts=[AccountSettings(name="home", email="home@example.com", password="secret")]
    )
    client = OrangeClient(settings)

    result = await client._classify(AuthenticatedDashboardRootPage())  # type: ignore[arg-type]  # noqa: SLF001

    assert result.status is LoginStatus.SUCCESS
