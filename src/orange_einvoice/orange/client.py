from __future__ import annotations

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from orange_einvoice.config import AccountSettings, Settings
from orange_einvoice.models import LoginResult, LoginStatus
from orange_einvoice.orange import selectors
from orange_einvoice.orange.parser import classify_page, parse_next_required_login


class OrangeClient:
    """Orange-specific login boundary. It never controls browser lifecycle or schedules work."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def ensure_login(self, page: Page, account: AccountSettings, otp: str | None = None) -> LoginResult:
        try:
            await page.goto(self.settings.login_url, wait_until="domcontentloaded")
            before = await self._classify(page)
            if before.status is LoginStatus.SUCCESS:
                return before
            if before.status is LoginStatus.OTP_REQUIRED and otp:
                await page.locator(selectors.OTP_INPUT).first.fill(otp)
                await page.locator(selectors.SUBMIT_BUTTON).first.click()
            elif before.status is not LoginStatus.OTP_REQUIRED:
                await page.locator(selectors.EMAIL_INPUT).first.fill(str(account.email))
                await page.locator(selectors.PASSWORD_INPUT).first.fill(account.password.get_secret_value())
                await page.locator(selectors.SUBMIT_BUTTON).first.click()
            await page.wait_for_timeout(1_000)
            return await self._classify(page)
        except PlaywrightTimeoutError:
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="browser timeout")
        except PlaywrightError as exc:
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail=f"browser error: {exc}")

    async def _classify(self, page: Page) -> LoginResult:
        text = await page.locator("body").inner_text()
        status = classify_page(text)
        return LoginResult(status, parse_next_required_login(text) if status is LoginStatus.SUCCESS else None)
