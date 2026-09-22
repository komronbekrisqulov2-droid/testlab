"""
Foydalanuvchilarning taklif va muammolari (Feedback) handleri.

O'quvchi va o'qituvchilar bot orqali bevosita administratorga
taklif yoki xatolik haqida xabar (matn yoki rasm/skrinshot)
yuborishi mumkin. Admin esa bot ichidan to'g'ridan-to'g'ri foydalanuvchiga
javob qaytara oladi.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.keyboards.callbacks import FeedbackCB
from apps.bot.keyboards.inline import admin_feedback_reply_keyboard, home_keyboard
from apps.bot.states import AdminFeedbackReplyState, FeedbackState
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.config import settings
from core.logging import get_logger
from modules.identity.models import User

log = get_logger(__name__)

router = Router(name="feedback")


# ======================================================================
#  1. TAKLIF VA MUAMMO QABUL QILISHNI BOSHLASH
# ======================================================================

@router.callback_query(FeedbackCB.filter(F.action == "open"))
async def open_feedback_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Inline tugma orqali taklif/muammo oynasini ochish."""
    await safe_answer(callback)
    await state.clear()
    await state.set_state(FeedbackState.waiting_for_message)
    await safe_edit(callback, uz.FEEDBACK_PROMPT, reply_markup=home_keyboard())


@router.message(Command("feedback"))
async def open_feedback_command(
    message: Message,
    state: FSMContext,
) -> None:
    """/feedback buyrug'i orqali ochish."""
    await state.clear()
    await state.set_state(FeedbackState.waiting_for_message)
    await message.answer(uz.FEEDBACK_PROMPT, reply_markup=home_keyboard())


# ======================================================================
#  2. FOYDALANUVCHIDAN XABARNI QABUL QILISH VA ADMINGA YUBORISH
# ======================================================================

async def _send_feedback_to_admins(
    message: Message,
    user: User,
    *,
    text: str | None = None,
    photo_file_id: str | None = None,
    document_file_id: str | None = None,
) -> None:
    """Barcha adminlarga bildirishnomani yetkazadi."""
    admins = list(settings.bot.admins)
    if not admins:
        log.warning("Adminlar ro'yxati (.env) bo'sh, taklif yetkazilmadi.")
        return

    admin_keyboard = admin_feedback_reply_keyboard(user.telegram_id)
    caption = uz.feedback_admin_notification(
        user,
        text=text,
        has_media=bool(photo_file_id or document_file_id),
    )

    for admin_id in admins:
        try:
            if photo_file_id:
                await message.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo_file_id,
                    caption=caption[:1024],
                    reply_markup=admin_keyboard,
                )
            elif document_file_id:
                await message.bot.send_document(
                    chat_id=admin_id,
                    document=document_file_id,
                    caption=caption[:1024],
                    reply_markup=admin_keyboard,
                )
            else:
                await message.bot.send_message(
                    chat_id=admin_id,
                    text=caption,
                    reply_markup=admin_keyboard,
                )
        except Exception as err:
            log.warning("Adminga (%s) murojaat yetkazilmadi: %s", admin_id, err)


@router.message(FeedbackState.waiting_for_message, F.text)
async def process_feedback_text(
    message: Message,
    state: FSMContext,
    user: User,
) -> None:
    """Matnli murojaatni qabul qilish."""
    text = (message.text or "").strip()

    if text.startswith("/cancel"):
        await state.clear()
        await message.answer(uz.CANCELLED, reply_markup=home_keyboard())
        return

    await state.clear()
    await _send_feedback_to_admins(message, user, text=text)
    await message.answer(uz.FEEDBACK_SENT, reply_markup=home_keyboard())
    log.info("📩 Taklif/muammo qabul qilindi: user=%s", user.telegram_id)


@router.message(FeedbackState.waiting_for_message, F.photo)
async def process_feedback_photo(
    message: Message,
    state: FSMContext,
    user: User,
) -> None:
    """Rasmli/skrinshotli murojaatni qabul qilish."""
    photo = message.photo[-1]
    await state.clear()
    await _send_feedback_to_admins(
        message,
        user,
        text=message.caption,
        photo_file_id=photo.file_id,
    )
    await message.answer(uz.FEEDBACK_SENT, reply_markup=home_keyboard())
    log.info("📩 Rasmli taklif/muammo qabul qilindi: user=%s", user.telegram_id)


@router.message(FeedbackState.waiting_for_message, F.document)
async def process_feedback_document(
    message: Message,
    state: FSMContext,
    user: User,
) -> None:
    """Faylli murojaatni qabul qilish."""
    document = message.document
    await state.clear()
    await _send_feedback_to_admins(
        message,
        user,
        text=message.caption,
        document_file_id=document.file_id,
    )
    await message.answer(uz.FEEDBACK_SENT, reply_markup=home_keyboard())
    log.info("📩 Faylli taklif/muammo qabul qilindi: user=%s", user.telegram_id)


# ======================================================================
#  3. ADMINNING FOYDALANUVCHIGA JAVOB YO'LLASHI
# ======================================================================

@router.callback_query(FeedbackCB.filter(F.action == "reply"))
async def start_admin_feedback_reply(
    callback: CallbackQuery,
    callback_data: FeedbackCB,
    state: FSMContext,
    user: User,
) -> None:
    """Admin 'Foydalanuvchiga javob berish' tugmasini bosganda."""
    await safe_answer(callback)

    if not (user.is_admin or settings.bot.is_admin(callback.from_user.id)):
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await state.set_state(AdminFeedbackReplyState.waiting_for_reply)
    await state.update_data(target_user_id=callback_data.target_id)

    if callback.message:
        await callback.message.answer(
            f"✍️ <b>Foydalanuvchiga javob yozish</b>\n"
            f"{uz.LINE}\n\n"
            f"Foydalanuvchi ID: <code>{callback_data.target_id}</code>\n\n"
            f"Javob matningizni yuboring:\n"
            f"<i>Bekor qilish: /cancel</i>"
        )


@router.message(AdminFeedbackReplyState.waiting_for_reply, F.text)
async def process_admin_feedback_reply(
    message: Message,
    state: FSMContext,
    user: User,
) -> None:
    """Admin yozgan javobni foydalanuvchiga yetkazish."""
    reply_text = (message.text or "").strip()

    if reply_text.startswith("/cancel"):
        await state.clear()
        await message.answer("✖️ Javob yuborish bekor qilindi.")
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    if not target_user_id:
        await message.answer("⚠️ Maqsadli foydalanuvchi aniqlanmadi.")
        return

    try:
        user_message_text = uz.feedback_user_reply(reply_text)
        await message.bot.send_message(
            chat_id=target_user_id,
            text=user_message_text,
        )
        await message.answer(
            f"✅ <b>Javobingiz foydalanuvchiga yetkazildi!</b>\n\n"
            f"Foydalanuvchi: <code>{target_user_id}</code>"
        )
        log.info(
            "Admin (%s) foydalanuvchiga (%s) javob yo'lladi.",
            user.telegram_id,
            target_user_id,
        )
    except Exception as err:
        log.warning("Foydalanuvchiga javob yetkazilmadi (%s): %s", target_user_id, err)
        await message.answer(
            f"⚠️ <b>Javob yetkazilmadi.</b>\n"
            f"Foydalanuvchi botni bloklagan bo'lishi mumkin:\n<code>{err}</code>"
        )
