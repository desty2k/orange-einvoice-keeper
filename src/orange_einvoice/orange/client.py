from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from orange_einvoice.config import AccountSettings, Settings
from orange_einvoice.models import LoginResult, LoginStatus
from orange_einvoice.orange import selectors
from orange_einvoice.orange.parser import classify_page, parse_next_required_login

logger = logging.getLogger(__name__)


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
            logger.info(
                "orange_initial_page_classified",
                extra={"account": account.name, "outcome": result.status.value},
            )
            if result.status is LoginStatus.SUCCESS:
                return result
            if result.status is LoginStatus.OTP_REQUIRED:
                return await self.submit_otp(page, otp) if otp else result
            return await self._submit_credentials(page, account)
        except PlaywrightTimeoutError:
            logger.info("orange_login_browser_timeout", extra={"account": account.name})
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="browser timeout")
        except PlaywrightError:
            logger.info("orange_login_browser_error", extra={"account": account.name})
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="browser error")

    async def submit_otp(self, page: Page, otp: str | None) -> LoginResult:
        """Resume the current OTP challenge without navigation or browser-context replacement."""
        try:
            if not otp:
                return LoginResult(LoginStatus.OTP_REQUIRED, detail="OTP required")
            fields = page.locator(selectors.OTP_INPUT)
            count = await fields.count()
            logger.info("orange_otp_field_layout", extra={"field_count": count})
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
            logger.info("orange_otp_filled")
            await page.locator(selectors.SUBMIT_BUTTON).first.click()
            logger.info("orange_otp_submit_clicked")
            return await self._wait_for_otp_resolution(page)
        except PlaywrightTimeoutError:
            logger.info("orange_otp_submission_timeout")
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="OTP submission timed out")
        except PlaywrightError:
            logger.info("orange_otp_submission_browser_error")
            return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="OTP browser error")

    async def _submit_credentials(self, page: Page, account: AccountSettings) -> LoginResult:
        """Use Orange's observed identifier → password sequence, without hard-coded DOM layout."""
        identifier = page.locator(selectors.IDENTIFIER_INPUT).first
        await identifier.wait_for(state="visible")
        await identifier.fill(str(account.email))
        await page.locator(selectors.SUBMIT_BUTTON).first.click()
        logger.info("orange_identifier_submit_clicked", extra={"account": account.name})

        # A remembered device can show OTP directly; otherwise wait only for the password stage.
        deadline = asyncio.get_running_loop().time() + self.settings.browser_timeout_ms / 1000
        password = page.locator(selectors.PASSWORD_INPUT).first
        while asyncio.get_running_loop().time() < deadline:
            result = await self._classify(page)
            if result.status in {LoginStatus.OTP_REQUIRED, LoginStatus.INVALID_CREDENTIALS}:
                logger.info(
                    "orange_identifier_resolution_complete",
                    extra={"account": account.name, "outcome": result.status.value},
                )
                return result
            if await password.is_visible():
                await password.fill(account.password.get_secret_value())
                logger.info("orange_password_filled", extra={"account": account.name})
                await page.locator(selectors.SUBMIT_BUTTON).first.click()
                logger.info("orange_password_submit_clicked", extra={"account": account.name})
                return await self._wait_for_login_resolution(page)
            await page.wait_for_timeout(250)
        logger.info("orange_password_stage_timeout", extra={"account": account.name})
        return LoginResult(LoginStatus.TEMPORARY_FAILURE, detail="password stage did not appear")

    async def _wait_for_login_resolution(self, page: Page) -> LoginResult:
        """Wait through Orange's intermediary page after password submission."""
        return await self._wait_for_resolution(
            page,
            terminal={
                LoginStatus.OTP_REQUIRED,
                LoginStatus.SUCCESS,
                LoginStatus.INVALID_CREDENTIALS,
            },
            completion_event="orange_password_resolution_complete",
            transition_event="orange_password_transition_dom_unavailable",
        )

    async def _wait_for_otp_resolution(self, page: Page) -> LoginResult:
        """Wait through OTP and intermediary screens for a final authentication result."""
        return await self._wait_for_resolution(
            page,
            terminal={LoginStatus.SUCCESS, LoginStatus.INVALID_CREDENTIALS},
            completion_event="orange_otp_resolution_complete",
            transition_event="orange_otp_transition_dom_unavailable",
        )

    async def _wait_for_resolution(
        self,
        page: Page,
        *,
        terminal: set[LoginStatus],
        completion_event: str,
        transition_event: str,
    ) -> LoginResult:
        """Poll navigation safely; short DOM-read timeouts are normal during transitions."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + self.settings.browser_timeout_ms / 1000
        last_result: LoginResult | None = None
        transition_logged = False

        while loop.time() < deadline:
            remaining_ms = max(1, round((deadline - loop.time()) * 1000))
            try:
                result = await self._classify(page, timeout_ms=min(1_000, remaining_ms))
                last_result = result
                if result.status in terminal:
                    self._log_resolution(completion_event, result, started)
                    return result
            except PlaywrightTimeoutError:
                if not transition_logged:
                    logger.info(transition_event)
                    transition_logged = True
            await page.wait_for_timeout(250)

        result = last_result or LoginResult(
            LoginStatus.TEMPORARY_FAILURE,
            detail="Orange post-submit page did not settle",
        )
        self._log_resolution(completion_event, result, started)
        return result

    @staticmethod
    def _log_resolution(event: str, result: LoginResult, started: float) -> None:
        logger.info(
            event,
            extra={
                "outcome": result.status.value,
                "waited_ms": round((asyncio.get_running_loop().time() - started) * 1000),
            },
        )

    async def _classify(self, page: Page, *, timeout_ms: int | None = None) -> LoginResult:
        text = await page.locator("body").inner_text(timeout=timeout_ms)
        otp_fields = page.locator(selectors.OTP_INPUT)
        has_otp_input = await otp_fields.count() > 0 and await otp_fields.first.is_visible()
        status = classify_page(text, has_otp_input=has_otp_input)
        deadline = parse_next_required_login(text) if status is LoginStatus.SUCCESS else None
        return LoginResult(status, deadline)
