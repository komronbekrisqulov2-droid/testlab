"""
Ota-ona va repetitorga avtomatik hisobot berish boshqaruvi.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import IsRegistered
from apps.bot.keyboards.callbacks import ParentCB
from apps.bot.keyboards.inline import home_keyboard, parent_hub_keyboard
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.logging import get_logger
from modules.identity.models import User
from modules.identity.repository import UserRepository

log = get_logger(__name__)

router = Router(name="student_parent")
router.message.filter(IsRegistered())
router.callback_query.filter(IsRegistered())


@router.callback_query(ParentCB.filter(F.action == "hub"))
async def open_parent_hub(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Ota-ona ulash ekrani."""
    await safe_answer(callback)

    users = UserRepository(session)
    parents = await users.get_parent_links(user.id)

    bot_info = await callback.bot.get_me()
    link_url = f"https://t.me/{bot_info.username}?start=parent_{user.telegram_id}"

    await safe_edit(
        callback,
        uz.parent_hub_text(link_url, parents),
        reply_markup=parent_hub_keyboard(parents),
    )


@router.callback_query(ParentCB.filter(F.action == "unlink"))
async def unlink_parent(
    callback: CallbackQuery,
    callback_data: ParentCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Ota-onani hisobdan uzish."""
    users = UserRepository(session)
    await users.unlink_parent(user.id, callback_data.target_id)

    await safe_answer(callback, "❌ Nazoratchi hisobdan uzildi.", alert=True)
    await open_parent_hub(callback, user, session)


async def handle_parent_deeplink(
    message: Message,
    student_telegram_id: int,
    parent_user: User,
    session: AsyncSession,
) -> bool:
    """
    Ota-ona yoki repetitor `t.me/bot?start=parent_<student_id>` havolasi orqali kirganda.
    """
    users = UserRepository(session)
    student = await users.get_by_telegram_id(student_telegram_id)

    if student is None:
        await message.answer("⚠️ O'quvchi hisobi topilmadi.", reply_markup=home_keyboard())
        return True

    if student.id == parent_user.id:
        await message.answer(
            "⚠️ O'zingizni o'zingizga nazoratchi qilib ulay olmaysiz! "
            "Ushbu havolani ota-onangiz yoki repetitoringizga yuboring.",
            reply_markup=home_keyboard(),
        )
        return True

    # Bog'lanishni saqlash
    await users.link_parent(
        student_id=student.id,
        parent_telegram_id=parent_user.telegram_id,
        parent_name=parent_user.full_name,
        relationship_type="parent",
    )

    # Ota-onaga tasdiq
    await message.answer(
        uz.parent_linked_msg(student.full_name),
        reply_markup=home_keyboard(),
    )

    # O'quvchiga ham xushxabar bildirishnoma
    try:
        await message.bot.send_message(
            student.telegram_id,
            f"👨‍👩‍👧 <b>YANGI NAZORATCHI ULANDI</b>\n"
            f"{uz.LINE}\n\n"
            f"<b>{uz.escape(parent_user.full_name)}</b> sizning profilingizga muvaffaqiyatli ulandi!\n"
            f"Endi topshirgan testlaringiz natijasi ularga ham avtomatik boradi.",
        )
    except Exception as err:
        log.debug("O'quvchiga ota-ona ulanish xabari yetkazilmadi: %s", err)

    return True
