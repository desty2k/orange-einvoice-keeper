from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import Page

from orange_einvoice.browser import BrowserFactory
from orange_einvoice.config import AccountSettings, Settings
from orange_einvoice.models import AccountState, LoginResult, LoginStatus, NotificationEvent
from orange_einvoice.notifications import Notifier
from orange_einvoice.orange import OrangeClient
from orange_einvoice.state import SQLiteStateRepository
from orange_einvoice.state_machine import transition

logger = logging.getLogger(__name__)
OTPProvider = Callable[[], str]


class Runner:
    def __init__(
        self,
        settings: Settings,
        repository: SQLiteStateRepository,
        browser: BrowserFactory,
        orange: OrangeClient,
        notifier: Notifier,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.browser = browser
        self.orange = orange
        self.notifier = notifier

    async def process(
        self, account: AccountSettings, state: AccountState, otp: str | None = None
    ) -> AccountState:
        try:
            async with self.browser.session(account) as session:
                result = await self.orange.ensure_login(session.page, account, otp)
                await self._capture_if_unexpected(account.name, session.page, result)
        except Exception as exc:  # Application boundary: cleanup and retry are guaranteed.
            logger.exception("account_run_failed", extra={"account": account.name})
            result = LoginResult(
                LoginStatus.TEMPORARY_FAILURE,
                detail=f"unexpected runtime error: {type(exc).__name__}",
            )
        return await self._record_outcome(account, state, result)

    async def bootstrap(
        self,
        account: AccountSettings,
        state: AccountState,
        otp: str | None = None,
        prompt_otp: OTPProvider | None = None,
    ) -> AccountState:
        """Interactively resolve OTP while retaining the exact active page and browser context."""
        try:
            async with self.browser.session(account) as session:
                result = await self.orange.ensure_login(session.page, account)
                if result.status is LoginStatus.OTP_REQUIRED:
                    code = otp if otp is not None else prompt_otp().strip() if prompt_otp else ""
                    if code:
                        result = await self.orange.submit_otp(session.page, code)
                await self._capture_if_unexpected(account.name, session.page, result)
        except Exception as exc:  # Application boundary: cleanup and retry are guaranteed.
            logger.exception("bootstrap_failed", extra={"account": account.name})
            result = LoginResult(
                LoginStatus.TEMPORARY_FAILURE,
                detail=f"unexpected bootstrap error: {type(exc).__name__}",
            )
        return await self._record_outcome(account, state, result)

    async def _record_outcome(
        self, account: AccountSettings, state: AccountState, result: LoginResult
    ) -> AccountState:
        now = datetime.now(UTC)
        new_state = transition(state, result, self.settings, now)
        self.repository.update(new_state, f"LOGIN_{result.status.value.upper()}", result.detail)
        logger.info(
            "login_outcome",
            extra={
                "account": account.name,
                "outcome": result.status.value,
                "next_attempt_at": str(new_state.next_attempt_at),
            },
        )
        if result.status is not LoginStatus.SUCCESS:
            await self.notifier.notify(
                NotificationEvent(result.status.value.upper(), account.name, result.detail)
            )
        return new_state

    async def _capture_if_unexpected(
        self, account_name: str, page: Page, result: LoginResult
    ) -> None:
        expected = {LoginStatus.SUCCESS, LoginStatus.OTP_REQUIRED, LoginStatus.INVALID_CREDENTIALS}
        if result.status not in expected:
            await self._save_artifact(account_name, page, result.detail)

    async def _save_artifact(self, account_name: str, page: Page, detail: str | None) -> None:
        artifact = (
            self.settings.data_dir
            / "artifacts"
            / account_name
            / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        )
        artifact.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(artifact / "screenshot.png"), full_page=True)
            if self.settings.save_failure_html:
                (artifact / "page.html").write_text(await page.content(), encoding="utf-8")
            (artifact / "metadata.json").write_text(
                json.dumps({"detail": detail}, indent=2), encoding="utf-8"
            )
            self._trim_artifacts(artifact.parent)
        except Exception:
            logger.exception("artifact_capture_failed", extra={"account": account_name})

    def _trim_artifacts(self, root: Path) -> None:
        existing = sorted(path for path in root.iterdir() if path.is_dir())
        retention = self.settings.failure_artifact_retention
        stale = existing[:-retention] if retention else existing
        for directory in stale:
            for child in directory.iterdir():
                child.unlink()
            directory.rmdir()
