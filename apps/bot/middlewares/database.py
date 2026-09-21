"""Baza sessiyasi middleware'i."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from core.logging import get_logger
from infrastructure.database.engine import session_factory

log = get_logger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """
    Har bir update uchun BITTA sessiya ochadi.

        handler xatosiz tugadi  ->  commit
        xato yuz berdi          ->  rollback
        har qanday holatda      ->  sessiya yopiladi

    Nega bitta sessiya? Chunki bitta so'rovdagi barcha o'zgarishlar
    bitta tranzaksiyada bo'lishi kerak. Masalan test yaratilib, XP
    berilib, keyin xato chiqsa — ikkalasi ham bekor bo'ladi, yarim
    yozilgan holat qolmaydi.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with session_factory() as session:
            data["session"] = session

            try:
                result = await handler(event, data)
                await session.commit()
                return result

            except Exception:
                await session.rollback()
                raise
