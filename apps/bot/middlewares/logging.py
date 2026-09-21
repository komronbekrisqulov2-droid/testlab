"""Har bir update'ni yozib borish."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.logging import get_logger

log = get_logger("bot.updates")

#  Sekin ishlagan handler ogohlantiriladi (soniya)
SLOW_THRESHOLD = 2.0


class LoggingMiddleware(BaseMiddleware):
    """
    Kim nima qilganini va qancha vaqt ketganini yozadi.

    Sekin ishlagan handler alohida belgilanadi — muammoni keyin
    qidirib o'tirmaslik uchun.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")
        user_id = telegram_user.id if telegram_user else 0

        description = self._describe(event)
        started = time.monotonic()

        try:
            return await handler(event, data)

        finally:
            elapsed = time.monotonic() - started

            if elapsed >= SLOW_THRESHOLD:
                log.warning("🐢 %s: %s (%.2fs)", user_id, description, elapsed)
            else:
                log.info("%s: %s", user_id, description)

    @staticmethod
    def _describe(event: TelegramObject) -> str:
        """Update'ni qisqa matn bilan ta'riflaydi."""
        if isinstance(event, Message):
            if event.text:
                #  Uzun xabarni kesamiz — log fayli shishib ketmasin
                text = event.text[:60].replace("\n", " ")
                suffix = "…" if len(event.text) > 60 else ""
                return f"xabar «{text}{suffix}»"
            if event.photo:
                return "rasm"
            if event.document:
                return f"fayl ({event.document.mime_type})"
            if event.contact:
                return "kontakt"
            return "xabar (boshqa tur)"

        if isinstance(event, CallbackQuery):
            return f"tugma [{event.data}]"

        return type(event).__name__
