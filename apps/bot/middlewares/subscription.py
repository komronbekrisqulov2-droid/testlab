"""
Majburiy obuna tekshiruvi.

`.env` dagi `REQUIRED_CHANNELS` bo'sh bo'lsa bu middleware butunlay
chetlab o'tiladi — kodga tegmasdan yoqib-o'chirish mumkin.

NEGA KESH KERAK
---------------
Telegram'da a'zolikni bilishning yagona yo'li — `get_chat_member`
so'rovi. Har bir tugma bosishida har bir kanal uchun so'rov yuborilsa:

  * botning javobi sezilarli sekinlashadi (har so'rov ~100-300 ms),
  * Telegram chegarasi tez to'ladi va bot vaqtincha bloklanadi.

Shuning uchun MUSBAT javob qisqa muddatga eslab qolinadi. Manfiy javob
keshlanmaydi: foydalanuvchi endigina obuna bo'lib «Tekshirish» tugmasini
bosganda darhol o'tishi kerak, kesh muddati tugashini kutmasdan.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject

from apps.bot.keyboards.callbacks import MenuCB
from apps.bot.texts import uz
from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)

#  A'zolik tasdiqlangach shu muddat davomida qayta so'ralmaydi.
#  5 daqiqa — foydalanuvchi kanaldan chiqib ketsa ham uzoq kutilmaydi,
#  lekin oddiy seansda so'rovlar soni o'nlab marta kamayadi.
CACHE_TTL_SEC = 300

#  Kanalda "a'zo" deb hisoblanadigan holatlar. `left` va `kicked` yo'q.
MEMBER_STATUSES = frozenset({"creator", "administrator", "member", "restricted"})

#  «Obunani tekshirish» tugmasi. U ham tekshiruvdan o'tadi (obuna
#  bo'lmagan odamni o'tkazib yuborish mantiqsiz), lekin javob boshqacha:
#  «hali a'zo bo'lmadingiz» deb aniq aytiladi, aks holda tugma
#  ishlamayotgandek tuyuladi.
RECHECK_ACTION = "check_sub"


class SubscriptionMiddleware(BaseMiddleware):
    """Majburiy kanallarga a'zolikni tekshiradi."""

    def __init__(self) -> None:
        self.channels = settings.bot.channels
        self.enabled = settings.bot.subscription_required

        #  {telegram_id: tekshiruv eskiradigan vaqt}
        self._verified: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.enabled:
            return await handler(event, data)

        telegram_user = data.get("event_from_user")
        if telegram_user is None or telegram_user.is_bot:
            return await handler(event, data)

        #  Adminlar tekshirilmaydi: bot sozlamalarini boshqaradigan
        #  odam o'z sozlamasi tufayli qulflanib qolmasligi kerak
        if settings.bot.is_admin(telegram_user.id):
            return await handler(event, data)

        bot: Bot | None = data.get("bot")
        if bot is None:
            #  Bot obyektisiz tekshirib bo'lmaydi — qulflab qo'ymaymiz
            return await handler(event, data)

        if self._is_cached(telegram_user.id):
            return await handler(event, data)

        missing = await self._missing_channels(bot, telegram_user.id)

        if not missing:
            self._remember(telegram_user.id)
            return await handler(event, data)

        await self._show_lock(event, missing, retried=self._is_recheck(event))
        return None

    # ------------------------------------------------------------------
    #  Kesh
    # ------------------------------------------------------------------

    def _is_cached(self, telegram_id: int) -> bool:
        expires = self._verified.get(telegram_id)
        if expires is None:
            return False

        if expires < time.monotonic():
            self._verified.pop(telegram_id, None)
            return False

        return True

    def _remember(self, telegram_id: int) -> None:
        self._verified[telegram_id] = time.monotonic() + CACHE_TTL_SEC

        #  Xotira cheksiz o'smasin — eskirganlarni vaqti-vaqti bilan
        #  tozalaymiz (throttling middleware'idagi kabi)
        if len(self._verified) > 10_000:
            now = time.monotonic()
            for key in [k for k, v in self._verified.items() if v < now]:
                self._verified.pop(key, None)

    # ------------------------------------------------------------------
    #  Tekshiruv
    # ------------------------------------------------------------------

    async def _missing_channels(self, bot: Bot, telegram_id: int) -> list[str]:
        """
        Qaysi kanallarga obuna bo'lmagan.

        Xato bo'lsa (bot kanalda admin emas, kanal o'chirilgan, tarmoq
        uzildi) kanal TEKSHIRILGAN deb hisoblanadi. Sabab: sozlama
        xatosi tufayli butun bot ishlamay qolishidan ko'ra, obuna
        tekshiruvi ishlamagani yaxshiroq.
        """
        missing: list[str] = []

        for channel in self.channels:
            try:
                member = await bot.get_chat_member(channel, telegram_id)
            except Exception as error:
                log.warning("Obuna tekshirilmadi (%s): %s", channel, error)
                continue

            if member.status not in MEMBER_STATUSES:
                missing.append(channel)

        return missing

    @staticmethod
    def _is_recheck(event: TelegramObject) -> bool:
        """Bu «Obunani tekshirish» tugmasimi?"""
        if not isinstance(event, CallbackQuery) or not event.data:
            return False

        try:
            return MenuCB.unpack(event.data).action == RECHECK_ACTION
        except Exception:
            return False

    # ------------------------------------------------------------------
    #  Qulf ekrani
    # ------------------------------------------------------------------

    async def _show_lock(
        self,
        event: TelegramObject,
        missing: list[str],
        *,
        retried: bool,
    ) -> None:
        """Obuna talab qilinadigan ekranni ko'rsatadi."""
        from apps.bot.keyboards.inline import subscription_keyboard

        text = uz.subscription_required(missing)
        keyboard = subscription_keyboard(missing)

        try:
            if isinstance(event, CallbackQuery):
                #  Tekshirdi, lekin hali obuna bo'lmagan — buni
                #  qalqib chiquvchi xabar bilan aniq aytamiz, aks holda
                #  tugma «ishlamayotgandek» ko'rinadi
                if retried:
                    await event.answer(uz.SUBSCRIPTION_STILL_MISSING, show_alert=True)

                if event.message is not None:
                    await event.message.answer(text, reply_markup=keyboard)
                else:
                    await event.answer(uz.SUBSCRIPTION_SHORT, show_alert=True)

            elif isinstance(event, Message):
                await event.answer(text, reply_markup=keyboard)

        except Exception as error:
            log.debug("Obuna ekrani ko'rsatilmadi: %s", error)
