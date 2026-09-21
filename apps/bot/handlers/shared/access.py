"""
Huquqi yetmagan foydalanuvchilar uchun chiroyli javob.

MUAMMO
------
Router filtri (`HasPermission`) huquqi yo'q foydalanuvchini butun
routerdan chetlab o'tkazadi. Natijada uning xabari `fallback` ga
tushib "🤔 Tushunmadim" degan foydasiz javob chiqardi.

YECHIM
------
Bu router `teacher` routerlaridan KEYIN, `fallback` dan OLDIN turadi.
O'qituvchi bo'lganlar yuqoridagi routerda ushlanadi va bu yergacha
yetib kelmaydi. Yetib kelgani — demak huquqi yo'q, unga nima uchun
ekanini va qanday olishni tushuntiramiz.

Ustiga: foydalanuvchi bir bosishda administratorga so'rov yuboradi,
admin ham bir bosishda ruxsat beradi.
"""

from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import IsRegistered
from apps.bot.keyboards.callbacks import MenuCB
from apps.bot.keyboards.inline import (
    grant_teacher_keyboard,
    home_keyboard,
    teacher_request_keyboard,
)
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.config import settings
from core.logging import get_logger
from modules.identity.models import User

log = get_logger(__name__)

router = Router(name="access")
router.message.filter(IsRegistered())

#  Bir foydalanuvchi shuncha vaqtda bir marta so'rov yubora oladi.
#  Busiz adminni spam bilan ko'mib yuborish mumkin edi.
REQUEST_COOLDOWN_SEC = 3600

#  {telegram_id: oxirgi so'rov vaqti}
#  Bot qayta ishga tushsa tozalanadi — bu qabul qilinadigan xatti-harakat:
#  eng yomoni foydalanuvchi so'rovni bir marta ortiqcha yuboradi.
_last_request: dict[int, float] = {}


def _on_cooldown(telegram_id: int) -> bool:
    last = _last_request.get(telegram_id)
    return last is not None and (time.monotonic() - last) < REQUEST_COOLDOWN_SEC


# ======================================================================
#  «TEST YARATISH» — HUQUQI YO'QLARGA
# ======================================================================

@router.message(Command("new"))
async def new_without_permission(message: Message) -> None:
    """
    /new — lekin o'qituvchi emas.

    O'qituvchilar bu yergacha yetib kelmaydi: ularni `teacher_create`
    routeri yuqorida ushlab qoladi.
    """
    await message.answer(uz.TEACHER_ONLY, reply_markup=teacher_request_keyboard())


@router.callback_query(MenuCB.filter(F.action == "create"))
async def create_without_permission(callback: CallbackQuery) -> None:
    """«➕ Test yaratish» tugmasi — lekin o'qituvchi emas."""
    await safe_answer(callback)
    await safe_edit(callback, uz.TEACHER_ONLY, reply_markup=teacher_request_keyboard())


@router.callback_query(MenuCB.filter(F.action == "mytests"))
async def my_tests_without_permission(callback: CallbackQuery) -> None:
    """«📚 Mening testlarim» — o'qituvchi emas."""
    await safe_answer(callback)
    await safe_edit(callback, uz.TEACHER_ONLY, reply_markup=teacher_request_keyboard())


# ======================================================================
#  SO'ROV YUBORISH
# ======================================================================

@router.callback_query(MenuCB.filter(F.action == "request_teacher"))
async def request_teacher(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Administratorga o'qituvchi huquqi uchun so'rov yuboradi.

    Admin keladigan xabarda «👨‍🏫 O'qituvchi qilish» tugmasi bo'ladi —
    panelga kirib qidirish shart emas.
    """
    await safe_answer(callback)

    if _on_cooldown(user.telegram_id):
        await safe_edit(
            callback,
            uz.REQUEST_ALREADY_SENT,
            reply_markup=home_keyboard(),
        )
        return

    if not settings.bot.admins:
        await safe_edit(
            callback,
            "⚠️ Hozircha administrator ko'rsatilmagan.\n\n"
            "Iltimos, keyinroq urinib ko'ring.",
            reply_markup=home_keyboard(),
        )
        return

    text = uz.teacher_request_for_admin(user)
    keyboard = grant_teacher_keyboard(user.id)

    delivered = 0

    for admin_id in settings.bot.admins:
        try:
            await callback.bot.send_message(admin_id, text, reply_markup=keyboard)
            delivered += 1
        except Exception as error:
            #  Admin hali botga /start bosmagan bo'lishi mumkin
            log.debug("So'rov yetkazilmadi (%s): %s", admin_id, error)

    if delivered == 0:
        await safe_edit(
            callback,
            "⚠️ Administrator bilan bog'lanib bo'lmadi.\n\n"
            "Iltimos, keyinroq urinib ko'ring.",
            reply_markup=home_keyboard(),
        )
        return

    _last_request[user.telegram_id] = time.monotonic()

    log.info(
        "📩 O'qituvchi so'rovi: %s (%s) -> %d ta adminga",
        user.telegram_id, user.full_name, delivered,
    )

    await safe_edit(callback, uz.REQUEST_SENT, reply_markup=home_keyboard())
