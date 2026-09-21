"""Foydalanuvchini yuklash va kirish huquqini tekshirish."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TelegramUser

from apps.bot.texts import uz
from core.config import settings
from core.logging import get_logger
from core.security.permissions import Role
from modules.identity.repository import UserRepository

log = get_logger(__name__)


class UserMiddleware(BaseMiddleware):
    """
    Har bir so'rovda:

        1. Foydalanuvchini bazadan topadi yoki yaratadi
        2. `.env` dagi adminlarga admin rolini beradi
        3. Bloklangan foydalanuvchini to'xtatadi
        4. Faollik vaqtini yangilaydi
        5. `user` obyektini handler'ga uzatadi
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user: TelegramUser | None = data.get("event_from_user")

        #  Foydalanuvchisiz hodisalar (kanal postlari) — o'tkazamiz
        if telegram_user is None or telegram_user.is_bot:
            return await handler(event, data)

        session = data.get("session")
        if session is None:
            #  DatabaseMiddleware ishlamagan — bu bo'lmasligi kerak
            log.error("UserMiddleware: sessiya topilmadi")
            return await handler(event, data)

        users = UserRepository(session)

        user, is_new = await users.get_or_create(
            telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )

        #  `.env` dagi adminlar bazadagi roldan qat'i nazar admin bo'ladi.
        #  Bu botni boshqarib bo'lmaydigan holatga tushib qolishdan
        #  himoya qiladi: rolni tasodifan o'zgartirib qo'ysangiz ham
        #  `.env` orqali qaytarasiz.
        if settings.bot.is_admin(telegram_user.id) and user.role != Role.ADMIN.value:
            if user.role != Role.SUPER_ADMIN.value:
                await users.set_role(user, Role.ADMIN.value)
                log.info("Admin roli berildi: %s", telegram_user.id)

        if is_new:
            log.info(
                "🆕 Yangi foydalanuvchi: %s (@%s)",
                telegram_user.id, telegram_user.username or "—",
            )

        # --- Bloklangan ---
        if user.is_banned:
            text = uz.BANNED
            if user.ban_reason:
                text += f"\n\n<i>Sabab: {uz.escape(user.ban_reason)}</i>"
            await self._notify(event, text)
            return None

        await users.touch(user, username=telegram_user.username)

        data["user"] = user
        data["is_new_user"] = is_new

        return await handler(event, data)

    @staticmethod
    async def _notify(event: TelegramObject, text: str) -> None:
        """Foydalanuvchiga xabar yuboradi (hodisa turiga qarab)."""
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(text[:200], show_alert=True)
            elif isinstance(event, Message):
                await event.answer(text)
        except Exception as error:
            log.debug("Ogohlantirish yuborilmadi: %s", error)
