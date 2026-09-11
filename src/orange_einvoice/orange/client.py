from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from orange_einvoice.config import AccountSettings, Settings
from orange_einvoice.models import LoginResult, LoginStatus
from orange_einvoice.orange import selectors
from orange_einvoice.orange.parser import classify_page, parse_next_required_login


class OrangeClient:
    """Orange-specific login boundary; browser lifecycle and scheduling live elsewhere."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def ensure_login(
        self, page: Page, account: AccountSettings, otp: str | None = None
    ) -> LoginResult:
        """Navigate once and either authenticate or identify an OTP challenge."""
        try:
            await page.goto(self.settings.login_url, wait_until="domcontentloaded")
            result = await self._classify(page)
            if result.status is LoginStatus.SUCCESS:
                return result
            if result.status is LoginStatus.OTP_REQUIRED:
                return await self.submit_otp(page, otp) if otp else result
            return await self._submit_credentials(page, account)
        except PlaywrightTimeoutError:
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="browser timeout")
        except PlaywrightError as exc:
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail=f"browser error: {exc}")

    async def submit_otp(self, page: Page, otp: str | None) -> LoginResult:
        """Resume the current OTP challenge without navigation or browser-context replacement."""
        try:
            if not otp:
                return LoginResult(LoginStatus.OTP_REQUIRED, detail="OTP required")
            fields = page.locator(selectors.OTP_INPUT)
            count = await fields.count()
            if count == 0:
                return LoginResult(LoginStatus.UNEXPECTED_PAGE, detail="OTP input was not found")
            if count == 1:
                await fields.first.wait_for(state="visible")
                await fields.first.fill(otp)
            elif count == len(otp):
                for index, character in enumerate(otp):
                    field = fields.nth(index)
                    await field.wait_for(state="visible")
                    await field.fill(character)
            else:
                return LoginResult(
                    LoginStatus.UNEXPECTED_PAGE,
                    detail=f"unsupported OTP input layout ({count} fields)",
                )
            await page.locator(selectors.SUBMIT_BUTTON).first.click()
            return await self._wait_for_otp_resolution(page)
        except PlaywrightTimeoutError:
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="OTP submission timed out")
        except PlaywrightError as exc:
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail=f"OTP browser error: {exc}")

    async def _submit_credentials(self, page: Page, account: AccountSettings) -> LoginResult:
        """Use Orange's observed identifier → password sequence, without hard-coded DOM layout."""
        identifier = page.locator(selectors.IDENTIFIER_INPUT).first
        await identifier.wait_for(state="visible")
        await identifier.fill(str(account.email))
        await page.locator(selectors.SUBMIT_BUTTON).first.click()

        # A remembered device can show OTP directly; otherwise wait only for the password stage.
        deadline = asyncio.get_running_loop().time() + self.settings.browser_timeout_ms / 1000
        password = page.locator(selectors.PASSWORD_INPUT).first
        while asyncio.get_running_loop().time() < deadline:
            result = await self._classify(page)
            if result.status in {LoginStatus.OTP_REQUIRED, LoginStatus.INVALID_CREDENTIALS}:
                return result
            if await password.is_visible():
                await password.fill(account.password.get_secret_value())
                await page.locator(selectors.SUBMIT_BUTTON).first.click()
                return await self._wait_for_otp_resolution(page)
            await page.wait_for_timeout(250)
        return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="password stage did not appear")

    async def _wait_for_otp_resolution(self, page: Page) -> LoginResult:
        """Allow Orange to process a submission instead of assuming a one-second response."""
        deadline = asyncio.get_running_loop().time() + self.settings.browser_timeout_ms / 1000
        result = await self._classify(page)
        while result.status is LoginStatus.OTP_REQUIRED and asyncio.get_running_loop().time() < deadline:
            await page.wait_for_timeout(250)
            result = await self._classify(page)
        return result

    async def _classify(self, page: Page) -> LoginResult:
        text = await page.locator("body").inner_text()
        otp_fields = page.locator(selectors.OTP_INPUT)
        has_otp_input = await otp_fields.count() > 0 and await otp_fields.first.is_visible()
        status = classify_page(text, has_otp_input=has_otp_input)
        deadline = parse_next_required_login(text) if status is LoginStatus.SUCCESS else None
        return LoginResult(status, deadline)
