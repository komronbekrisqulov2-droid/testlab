"""Spam va flood himoyasi."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from apps.bot.texts import uz
from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)

#  Ogohlantirish shu vaqt oralig'ida bir marta yuboriladi.
#  Busiz spam qilayotgan foydalanuvchiga biz ham spam qilardik.
WARN_COOLDOWN = 5.0


class ThrottlingMiddleware(BaseMiddleware):
    """
    Sirg'aluvchi oyna (sliding window) usuli.

    Har bir foydalanuvchi uchun oxirgi so'rovlar vaqti saqlanadi.
    Oynadan chiqib ketganlari tashlanadi, qolgani sanaladi.

    Nega Redis emas? Bitta bot nusxasi uchun xotira yetarli va tezroq.
    Bir necha nusxa ishlatilsa Redis'ga o'tish kerak bo'ladi — interfeys
    o'zgarmaydi.
    """

    def __init__(self) -> None:
        self.rate = settings.security.throttle_rate
        self.period = float(settings.security.throttle_period)

        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._warned: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")

        if telegram_user is None or telegram_user.is_bot:
            return await handler(event, data)

        #  Adminlar cheklanmaydi — ommaviy xabar yuborishda o'zini
        #  bloklab qo'ymasligi uchun
        if settings.bot.is_admin(telegram_user.id):
            return await handler(event, data)

        user_id = telegram_user.id
        now = time.monotonic()
        window = self._hits[user_id]

        #  Oynadan chiqqanlarni tashlaymiz
        threshold = now - self.period
        while window and window[0] < threshold:
            window.popleft()

        if len(window) >= self.rate:
            await self._warn(event, user_id, now)
            return None

        window.append(now)

        #  Xotira cheksiz o'smasligi uchun vaqti-vaqti bilan tozalaymiz
        if len(self._hits) > 10_000:
            self._cleanup(threshold)

        return await handler(event, data)

    async def _warn(self, event: TelegramObject, user_id: int, now: float) -> None:
        """Ogohlantiradi — lekin har safar emas."""
        last = self._warned.get(user_id, 0.0)
        if now - last < WARN_COOLDOWN:
            return

        self._warned[user_id] = now
        log.warning("Throttle: user=%s", user_id)

        try:
            if isinstance(event, CallbackQuery):
                await event.answer(uz.TOO_FAST, show_alert=False)
            elif isinstance(event, Message):
                await event.answer(uz.TOO_FAST)
        except Exception:
            pass

    def _cleanup(self, threshold: float) -> None:
        """Eskirgan yozuvlarni o'chiradi."""
        stale = [
            user_id
            for user_id, window in self._hits.items()
            if not window or window[-1] < threshold
        ]
        for user_id in stale:
            self._hits.pop(user_id, None)
            self._warned.pop(user_id, None)
