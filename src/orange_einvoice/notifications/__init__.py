from __future__ import annotations

import logging

import httpx

from orange_einvoice.models import NotificationEvent

logger = logging.getLogger(__name__)


class Notifier:
    async def notify(self, event: NotificationEvent) -> None:
        raise NotImplementedError


class NoopNotifier(Notifier):
    async def notify(self, event: NotificationEvent) -> None:
        logger.debug("notification_suppressed", extra={"event": event.event_type, "account": event.account_name})


class WebhookNotifier(Notifier):
    def __init__(self, url: str) -> None:
        self.url = url

    async def notify(self, event: NotificationEvent) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.url, json={"event": event.event_type, "account": event.account_name, "detail": event.detail})
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("notification_failed", extra={"account": event.account_name})
