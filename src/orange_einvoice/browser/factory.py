from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from playwright.async_api import BrowserContext, Page, async_playwright

from orange_einvoice.config import AccountSettings, Settings


@dataclass(slots=True)
class BrowserSession:
    context: BrowserContext
    page: Page


class BrowserFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @asynccontextmanager
    async def session(self, account: AccountSettings) -> AsyncIterator[BrowserSession]:
        profile = self.settings.data_dir / "browser" / account.name
        profile.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(profile),
                headless=self.settings.browser_headless,
                viewport={"width": 1440, "height": 1000},
                args=["--disable-dev-shm-usage"],
            )
            context.set_default_timeout(self.settings.browser_timeout_ms)
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                yield BrowserSession(context, page)
            finally:
                await context.close()
