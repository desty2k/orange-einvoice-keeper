from __future__ import annotations

import asyncio
import json
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from orange_einvoice.browser import BrowserFactory
from orange_einvoice.config import Settings
from orange_einvoice.models import AccountState
from orange_einvoice.notifications import NoopNotifier, WebhookNotifier
from orange_einvoice.orange import OrangeClient
from orange_einvoice.runner import Runner
from orange_einvoice.scheduler import Scheduler
from orange_einvoice.state import SQLiteStateRepository

logger = logging.getLogger(__name__)


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = SQLiteStateRepository(settings.data_dir / "state.db")
        self.shutdown_event = asyncio.Event()
        notifier = WebhookNotifier(settings.webhook_url) if settings.webhook_url else NoopNotifier()
        self.runner = Runner(settings, self.repository, BrowserFactory(settings), OrangeClient(settings), notifier)

    def start(self) -> None:
        now = datetime.now(UTC)
        self.repository.open()
        self.repository.reconcile(self.settings.accounts, now)
        self.repository.cap_success_schedules(self.settings.success_check_interval_days, now)

    def stop(self) -> None:
        self.shutdown_event.set()
        self.repository.close()

    async def run(self) -> None:
        self.start()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, self.shutdown_event.set)
        try:
            await Scheduler(self.repository, self.shutdown_event, self._process_state).run()
        finally:
            self.stop()

    async def run_once(self, account_name: str | None = None) -> list[AccountState]:
        self.start()
        try:
            selected = [account for account in self.settings.accounts if account.enabled and (account_name is None or account.name == account_name)]
            if account_name and not selected:
                raise ValueError(f"unknown or disabled account: {account_name}")
            result: list[AccountState] = []
            for account in selected:
                state = self.repository.get(account.name)
                if state is None:
                    raise RuntimeError(f"missing reconciled state for {account.name}")
                result.append(await self.runner.process(account, state))
            return result
        finally:
            self.repository.close()

    async def bootstrap(
        self,
        account_name: str,
        otp: str | None = None,
        prompt_otp: Callable[[], str] | None = None,
    ) -> AccountState:
        self.start()
        try:
            account = next(
                (
                    item
                    for item in self.settings.accounts
                    if item.name == account_name and item.enabled
                ),
                None,
            )
            if account is None:
                raise ValueError(f"unknown or disabled account: {account_name}")
            state = self.repository.get(account.name)
            if state is None:
                raise RuntimeError(f"missing reconciled state for {account.name}")
            return await self.runner.bootstrap(account, state, otp, prompt_otp)
        finally:
            self.repository.close()

    def status(self) -> dict[str, Any]:
        self.start()
        try:
            states = self.repository.all()
            bad = [state for state in states if state.status.value not in {"success", "ready", "disabled"}]
            overall = "healthy" if not bad else "degraded"
            return {"status": overall, "accounts": {state.account_name: self._serialize(state) for state in states}}
        finally:
            self.repository.close()

    async def _process_state(self, state: AccountState) -> None:
        account = next(account for account in self.settings.accounts if account.name == state.account_name)
        await self.runner.process(account, state)

    @staticmethod
    def _serialize(state: AccountState) -> dict[str, str | int | None]:
        return {"status": state.status.value, "last_success_at": str(state.last_success_at) if state.last_success_at else None,
                "next_attempt_at": str(state.next_attempt_at) if state.next_attempt_at else None,
                "consecutive_failures": state.consecutive_failures, "last_error": state.last_error}


def status_json(settings: Settings) -> str:
    return json.dumps(Application(settings).status(), indent=2)
