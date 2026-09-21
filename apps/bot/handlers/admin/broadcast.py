"""
Ommaviy xabar.

NEGA `copy_message`, MATN EMAS
------------------------------
Admin xabarni matn qilib qayta yozsa, formatlash, rasm va fayl
yo'qoladi. `copy_message` esa adminning YUBORGAN xabarini aynan
nusxalaydi: rasm rasm bo'lib, qalin matn qalin bo'lib boradi, va
«forwarded from» yozuvi ham chiqmaydi.

Shu sababli FSM'da xabar MATNI emas, uning manzili
(`chat_id` + `message_id`) saqlanadi.

TEZLIK
------
Telegram bir xil botdan turli foydalanuvchilarga sekundiga ~30 xabar
o'tkazadi. Undan tez yuborilsa `RetryAfter` keladi va butun bot
vaqtincha jazolanadi. Shuning uchun ataylab sekinroq — sekundiga 20 ta
— yuboriladi va `RetryAfter` kelsa aytilgan vaqt kutiladi.
"""

from __future__ import annotations

import asyncio
import time

from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import IsAdmin
from apps.bot.keyboards.admin import (
    broadcast_audience_keyboard,
    broadcast_confirm_keyboard,
    cancel_search_keyboard,
    panel_keyboard,
)
from apps.bot.keyboards.callbacks import AdminCB
from apps.bot.states import Broadcast
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.logging import get_logger
from core.security.permissions import Permission, Role
from modules.identity.models import User
from modules.identity.repository import UserRepository

log = get_logger(__name__)

router = Router(name="admin_broadcast")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

#  Sekundiga 20 ta xabar. Telegram chegarasi ~30, lekin unga tiralib
#  ishlash xavfli: boshqa handler'lar ham xabar yuboradi.
SEND_DELAY_SEC = 0.05

#  Jarayon shu qadamda bir marta yangilanadi. Har xabarda yangilash
#  yuborishdan ko'ra ko'proq so'rov talab qilardi.
PROGRESS_EVERY = 25

#  Kimga: 1 = test yarata oladiganlar, 0 = hamma
TEACHER_ROLES = [
    Role.TEACHER.value,
    Role.MODERATOR.value,
    Role.ADMIN.value,
    Role.SUPER_ADMIN.value,
]


def _roles_for(target: int) -> list[str] | None:
    return TEACHER_ROLES if target == 1 else None


def _audience_label(target: int) -> str:
    return "o'qituvchilar" if target == 1 else "hamma"


# ======================================================================
#  1. KIMGA
# ======================================================================

@router.callback_query(AdminCB.filter(F.action == "broadcast"))
async def choose_audience(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
) -> None:
    await safe_answer(callback)

    #  Panelga kirish `IsAdmin` bilan himoyalangan, lekin ommaviy
    #  xabar alohida huquq: moderator panelni ko'radi-yu, hammaga
    #  xabar yubora olmasligi kerak.
    if not user.can(Permission.ADMIN_BROADCAST):
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await state.clear()
    await safe_edit(
        callback,
        "📣 <b>OMMAVIY XABAR</b>\n"
        f"{uz.LINE}\n\n"
        "Xabar kimga yuborilsin?",
        reply_markup=broadcast_audience_keyboard(),
    )


# ======================================================================
#  2. XABARNI SO'RASH
# ======================================================================

@router.callback_query(AdminCB.filter(F.action == "broadcast_ask"))
async def ask_message(
    callback: CallbackQuery,
    callback_data: AdminCB,
    user: User,
    state: FSMContext,
) -> None:
    if not user.can(Permission.ADMIN_BROADCAST):
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await safe_answer(callback)

    await state.set_state(Broadcast.message)
    await state.update_data(target=callback_data.target_id)

    await safe_edit(callback, uz.BROADCAST_ASK, reply_markup=cancel_search_keyboard())


@router.message(Broadcast.message)
async def receive_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """
    Yuboriladigan xabarni qabul qiladi va ko'rib chiqishga qo'yadi.

    Xabarning O'ZI saqlanmaydi — faqat manzili. Yuborish paytida
    `copy_message` shu manzildan nusxa oladi.
    """
    data = await state.get_data()
    target = int(data.get("target", 0))

    users = UserRepository(session)
    recipients = await users.list_broadcast_targets(roles=_roles_for(target))

    if not recipients:
        await state.clear()
        await message.answer(uz.BROADCAST_EMPTY, reply_markup=panel_keyboard())
        return

    await state.set_state(Broadcast.confirm)
    await state.update_data(
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
        total=len(recipients),
    )

    await message.answer(
        uz.broadcast_preview(len(recipients), _audience_label(target)),
        reply_markup=broadcast_confirm_keyboard(),
    )


# ======================================================================
#  3. YUBORISH
# ======================================================================

@router.callback_query(AdminCB.filter(F.action == "broadcast_go"), Broadcast.confirm)
async def send_broadcast(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not user.can(Permission.ADMIN_BROADCAST):
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    if callback.message is None:
        return

    data = await state.get_data()
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    if source_chat_id is None or source_message_id is None:
        #  Bot qayta ishga tushgan va FSM xotirada yo'qolgan bo'lishi
        #  mumkin — yarim ma'lumot bilan yuborishdan ko'ra to'xtagan afzal
        await safe_answer(callback, uz.SESSION_EXPIRED, alert=True)
        await state.clear()
        return

    await safe_answer(callback, uz.BROADCAST_SENDING)
    await state.clear()

    target = int(data.get("target", 0))
    recipients = await UserRepository(session).list_broadcast_targets(
        roles=_roles_for(target)
    )

    #  Tranzaksiyani darhol yakunlaymiz: xabarlar tarqatish bir necha daqiqa
    #  davom etishi mumkin va bu vaqtda DB sessiyasi/qulflari ochiq turmasin.
    await session.commit()

    status = await callback.message.answer(uz.broadcast_progress(0, len(recipients)))

    sent, failed, elapsed = await _deliver(
        callback,
        recipients,
        source_chat_id=int(source_chat_id),
        source_message_id=int(source_message_id),
        status=status,
    )

    await status.edit_text(
        uz.broadcast_done(sent, failed, elapsed),
        reply_markup=panel_keyboard(),
    )

    log.info(
        "📣 Ommaviy xabar: admin=%s kimga=%s yetkazildi=%d xato=%d (%.1f s)",
        user.telegram_id, _audience_label(target), sent, failed, elapsed,
    )


async def _deliver(
    callback: CallbackQuery,
    recipients: list[int],
    *,
    source_chat_id: int,
    source_message_id: int,
    status: Message,
) -> tuple[int, int, float]:
    """
    Xabarni ro'yxat bo'ylab tarqatadi.

    Returns:
        (yetkazilgan, yetkazilmagan, ketgan vaqt)
    """
    bot = callback.bot
    started = time.monotonic()
    sent = failed = 0

    for index, telegram_id in enumerate(recipients, start=1):
        try:
            await bot.copy_message(
                chat_id=telegram_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            sent += 1

        except TelegramRetryAfter as error:
            #  Telegram aniq necha soniya kutishni aytadi — o'sha
            #  foydalanuvchiga qayta urinamiz, tashlab ketmaymiz
            log.warning("Ommaviy xabar sekinlashtirildi: %s s", error.retry_after)
            await asyncio.sleep(error.retry_after)

            try:
                await bot.copy_message(
                    chat_id=telegram_id,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                )
                sent += 1
            except Exception:
                failed += 1

        except Exception as error:
            #  Botni bloklagan yoki hisobini o'chirgan — normal holat
            failed += 1
            log.debug("Yetkazilmadi (%s): %s", telegram_id, error)

        if index % PROGRESS_EVERY == 0:
            try:
                await status.edit_text(uz.broadcast_progress(index, len(recipients)))
            except Exception:
                #  Matn o'zgarmagan yoki xabar o'chirilgan — jarayonni
                #  to'xtatishga arzimaydi
                pass

        await asyncio.sleep(SEND_DELAY_SEC)

    return sent, failed, time.monotonic() - started
