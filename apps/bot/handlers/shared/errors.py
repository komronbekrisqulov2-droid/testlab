"""Global xato ushlagich va tushunilmagan xabarlar."""

from __future__ import annotations

import secrets

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import CallbackQuery, ErrorEvent, Message

from apps.bot.keyboards.inline import home_keyboard
from apps.bot.texts import uz
from apps.bot.utils import safe_answer
from core.config import settings
from core.exceptions import TestLabError
from core.logging import get_logger

log = get_logger(__name__)
router = Router(name="errors")


# ======================================================================
#  DOMEN XATOLARI
# ======================================================================

@router.errors(ExceptionTypeFilter(TestLabError))
async def handle_domain_error(event: ErrorEvent) -> bool:
    """
    Biznes qoidasi buzilgan — bu KUTILGAN holat.

    Xato matni allaqachon foydalanuvchi uchun tayyor, shuning uchun
    traceback yozilmaydi: log faylini keraksiz shovqin bilan
    to'ldirmaymiz.
    """
    error: TestLabError = event.exception  # type: ignore[assignment]
    text = f"⚠️ {error.user_text()}"

    update = event.update

    if update.callback_query is not None:
        await safe_answer(update.callback_query, error.message[:200], alert=True)
    elif update.message is not None:
        try:
            await update.message.answer(text, reply_markup=home_keyboard())
        except Exception:
            pass

    log.info("Domen xatosi: %s", error.message)
    return True


# ======================================================================
#  FOYDALANUVCHI BOTNI BLOKLAGAN
# ======================================================================

@router.errors(ExceptionTypeFilter(TelegramForbiddenError))
async def handle_forbidden(event: ErrorEvent) -> bool:
    """
    Foydalanuvchi botni bloklagan yoki chatdan chiqib ketgan.

    Bu normal holat — xato sifatida yozilmaydi.
    """
    log.info("Foydalanuvchi botni bloklagan: %s", event.exception)
    return True


@router.errors(ExceptionTypeFilter(TelegramBadRequest))
async def handle_bad_request(event: ErrorEvent) -> bool:
    """Telegram so'rovni rad etdi — odatda eskirgan xabar."""
    log.warning("Telegram rad etdi: %s", event.exception)
    return True


# ======================================================================
#  KUTILMAGAN XATOLAR
# ======================================================================

@router.errors()
async def handle_unexpected(event: ErrorEvent) -> bool:
    """
    Kutilmagan xato.

    Foydalanuvchiga qisqa xato KODI beriladi. U koddan foydalanib
    murojaat qiladi, biz esa log'dan aynan shu holatni topamiz —
    "menda nimadir ishlamadi" degan murojaatni tekshirish osonlashadi.
    """
    error_id = secrets.token_hex(4).upper()

    log.exception(
        "💥 [%s] Kutilmagan xato: %s",
        error_id,
        event.exception,
        exc_info=event.exception,
    )

    update = event.update

    try:
        if update.callback_query is not None:
            await safe_answer(
                update.callback_query,
                f"❌ Xatolik. Kod: {error_id}",
                alert=True,
            )
        elif update.message is not None:
            await update.message.answer(
                uz.unknown_error(error_id), reply_markup=home_keyboard()
            )
    except Exception:
        pass

    #  Adminlarga xabar beramiz — muammoni ular birinchi bo'lib bilsin
    await _notify_admins(event, error_id)

    return True


async def _notify_admins(event: ErrorEvent, error_id: str) -> None:
    """Xato haqida adminlarga qisqacha xabar."""
    if not settings.bot.admins:
        return

    bot = event.update.bot
    if bot is None:
        return

    telegram_user = None
    if event.update.message is not None:
        telegram_user = event.update.message.from_user
    elif event.update.callback_query is not None:
        telegram_user = event.update.callback_query.from_user

    text = (
        f"💥 <b>Xatolik</b>\n"
        f"{uz.LINE}\n\n"
        f"<b>Kod:</b> <code>{error_id}</code>\n"
        f"<b>Tur:</b> <code>{type(event.exception).__name__}</code>\n"
        f"<b>Matn:</b> {uz.escape(str(event.exception)[:300])}\n"
    )

    if telegram_user:
        text += f"\n<b>Foydalanuvchi:</b> <code>{telegram_user.id}</code>"

    for admin_id in settings.bot.admins:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            #  Admin hali /start bosmagan bo'lishi mumkin — normal
            continue


# ======================================================================
#  TUSHUNILMAGAN XABARLAR — HAR DOIM OXIRIDA
# ======================================================================

fallback_router = Router(name="fallback")


@fallback_router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    """
    Eskirgan tugma.

    Bot qayta ishga tushgach eski xabardagi tugmalar ishlamay qolishi
    mumkin — foydalanuvchiga nima bo'lganini tushuntiramiz.
    """
    await safe_answer(callback, "⏳ Bu tugma eskirgan. /start bosing.", alert=True)


@fallback_router.message(F.text)
async def unknown_message(message: Message) -> None:
    await message.answer(uz.FALLBACK, reply_markup=home_keyboard())


@fallback_router.message()
async def unknown_content(message: Message) -> None:
    await message.answer(uz.FALLBACK, reply_markup=home_keyboard())
