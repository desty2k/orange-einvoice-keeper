from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime

from orange_einvoice.models import AccountState
from orange_einvoice.state import SQLiteStateRepository

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, repository: SQLiteStateRepository, shutdown_event: asyncio.Event,
                 process: Callable[[AccountState], Awaitable[None]]) -> None:
        self.repository, self.shutdown_event, self.process = repository, shutdown_event, process

    async def run(self) -> None:
        while not self.shutdown_event.is_set():
            due = self.repository.due_accounts(datetime.now(UTC))
            if due:
                for state in due:
                    if self.shutdown_event.is_set():
                        break
                    await self.process(state)
                continue
            next_run = self.repository.next_attempt()
            if next_run is None:
                await self._wait(3600)
            else:
                seconds = max(0, (next_run - datetime.now(UTC)).total_seconds())
                logger.info("scheduler_sleep", extra={"seconds": round(seconds), "next_attempt_at": str(next_run)})
                await self._wait(seconds)

    async def _wait(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self.shutdown_event.wait(), timeout=seconds)
