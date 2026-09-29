"""/start, ro'yxatdan o'tish va bosh menyu."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.keyboards.callbacks import MenuCB
from apps.bot.keyboards.inline import (
    home_keyboard,
    main_menu,
    register_keyboard,
    simple_back_keyboard,
)
from apps.bot.states import Registration
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.logging import get_logger
from modules.assessment.repository import AttemptRepository
from modules.identity.models import User
from modules.identity.repository import UserRepository

log = get_logger(__name__)
router = Router(name="start")

MIN_NAME_LEN = 5
MAX_NAME_LEN = 80


# ======================================================================
#  /start
# ======================================================================

@router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Havola orqali kirish: `t.me/bot?start=t12` yoki `?start=cert_TL-...`

    Bu posterdagi tugma va QR kod ishlaydigan joy — o'quvchi raqam
    terib o'tirmaydi, bitta bosishda test ochiladi.
    """
    await state.clear()

    payload = (command.args or "").strip()

    if not user.is_registered:
        #  Ro'yxatdan o'tgach havolani davom ettirish uchun eslab qolamiz
        await state.update_data(pending_payload=payload)
        await message.answer(uz.WELCOME_NEW, reply_markup=register_keyboard())
        return

    handled = await handle_payload(message, payload, user, session, state)

    if not handled:
        await show_main_menu(message, user, session)


async def handle_payload(
    message: Message,
    payload: str,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> bool:
    """
    Deep link yukini qayta ishlaydi.

    Returns:
        True — bajarildi, bosh menyu ko'rsatilmasin.
    """
    if not payload:
        return False

    #  --- Testga o'tish: t12 ---
    if payload.startswith("t") and payload[1:].isdigit():
        from apps.bot.handlers.student.answer import open_test
        from modules.catalog.service import CatalogService

        test = await CatalogService(session).tests.get_by_number(int(payload[1:]))

        if test is None:
            await message.answer(uz.DEEP_LINK_NOT_FOUND, reply_markup=home_keyboard())
            return True

        await open_test(message, test, user, session, state)
        return True

    #  --- Sertifikatni tekshirish: cert_TL-2026-XXXX ---
    if payload.startswith("cert_"):
        from core.exceptions import TestLabError
        from modules.certification.service import CertificateService

        try:
            certificate = await CertificateService(session).verify(payload[5:])
        except TestLabError as error:
            await message.answer(
                f"⚠️ {error.user_text()}", reply_markup=home_keyboard()
            )
            return True

        await message.answer(
            uz.certificate_verified(certificate), reply_markup=home_keyboard()
        )
        return True

    #  --- Ota-ona bog'lanishi: parent_123456789 ---
    if payload.startswith("parent_"):
        raw_id = payload[7:].strip()
        if raw_id.isdigit():
            from apps.bot.handlers.student.parent import handle_parent_deeplink

            return await handle_parent_deeplink(message, int(raw_id), user, session)

    return False


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Botni boshlash."""
    await state.clear()

    if not user.is_registered:
        await message.answer(uz.WELCOME_NEW, reply_markup=register_keyboard())
        return

    await show_main_menu(message, user, session)


@router.message(Command("menu"))
async def cmd_menu(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    await state.clear()

    if not user.is_registered:
        await message.answer(uz.WELCOME_NEW, reply_markup=register_keyboard())
        return

    await show_main_menu(message, user, session)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(uz.HELP, reply_markup=home_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    draft_id = data.get("draft_id")
    if draft_id:
        from modules.catalog.service import CatalogService

        catalog = CatalogService(session)
        draft = await catalog.tests.get(int(draft_id))
        if draft is not None and draft.is_draft and draft.author_id == user.id:
            try:
                await catalog.delete(draft, user)
                log.info("Bekor qilingan qoralama o'chirildi: №%s", draft.number)
            except Exception as error:
                log.warning("Qoralama o'chirilmadi: %s", error)

    await state.clear()
    await message.answer(uz.CANCELLED, reply_markup=ReplyKeyboardRemove())
    await show_main_menu(message, user, session)


# ======================================================================
#  BOSH MENYU
# ======================================================================

async def show_main_menu(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    """Bosh menyuni YANGI xabar sifatida yuboradi."""
    stats = await AttemptRepository(session).user_stats(user.id)
    await message.answer(uz.main_menu(user, stats), reply_markup=main_menu(user))


@router.callback_query(MenuCB.filter(F.action == "main"))
async def open_main_menu(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Bosh menyuga qaytish — mavjud xabarni tahrirlaydi."""
    await safe_answer(callback)

    data = await state.get_data()
    draft_id = data.get("draft_id")
    if draft_id:
        from modules.catalog.service import CatalogService

        catalog = CatalogService(session)
        draft = await catalog.tests.get(int(draft_id))
        if draft is not None and draft.is_draft and draft.author_id == user.id:
            try:
                await catalog.delete(draft, user)
                log.info("Bekor qilingan qoralama o'chirildi: №%s", draft.number)
            except Exception as error:
                log.warning("Qoralama o'chirilmadi: %s", error)

    await state.clear()

    stats = await AttemptRepository(session).user_stats(user.id)
    await safe_edit(callback, uz.main_menu(user, stats), reply_markup=main_menu(user))


@router.callback_query(MenuCB.filter(F.action == "help"))
async def open_help(callback: CallbackQuery) -> None:
    await safe_answer(callback)
    await safe_edit(callback, uz.HELP, reply_markup=simple_back_keyboard())


@router.callback_query(MenuCB.filter(F.action == "how_to_create"))
async def open_how_to_create(callback: CallbackQuery) -> None:
    """«❓ Test qanday yaratiladi?» bo'yicha batafsil ko'rsatma."""
    await safe_answer(callback)
    await safe_edit(callback, uz.HOW_TO_CREATE_TEXT, reply_markup=home_keyboard())


@router.message(Command("how_to_create", "create_help"))
async def cmd_how_to_create(message: Message) -> None:
    await message.answer(uz.HOW_TO_CREATE_TEXT, reply_markup=home_keyboard())


@router.callback_query(MenuCB.filter(F.action == "check_sub"))
async def check_subscription(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """
    «Obunani tekshirish» tugmasi.

    Bu handler'gacha yetib kelish o'zi javob: `SubscriptionMiddleware`
    a'zo bo'lmaganlarni yuqorida to'xtatadi va bu yergacha
    o'tkazmaydi. Demak foydalanuvchi obuna bo'lgan — uni tabriklab,
    darhol bosh menyuga o'tkazamiz.
    """
    await safe_answer(callback, "✅ Tekshirildi")

    if callback.message is not None:
        await callback.message.answer(uz.SUBSCRIPTION_OK)

    stats = await AttemptRepository(session).user_stats(user.id)
    await safe_edit(callback, uz.main_menu(user, stats), reply_markup=main_menu(user))


# ======================================================================
#  RO'YXATDAN O'TISH
# ======================================================================

def _validate_full_name(raw: str) -> tuple[tuple[str, str] | None, str | None]:
    """
    To'liq ism-familiyani tekshiradi.
    Kamida 2 ta so'z (ism va familiya) bo'lishi shart.
    O'zbek harflari (Oʻ, Gʻ, Sh, Ch) va turli apostrof shakllarini to'g'ri qabul qiladi.
    """
    if not raw or not isinstance(raw, str):
        return None, uz.FULL_NAME_INVALID

    # Barcha turdagi apostroflarni yagona standart apostrofga keltiramiz
    normalized = (
        raw.replace("`", "'")
        .replace("ʻ", "'")
        .replace("ʼ", "'")
        .replace("’", "'")
        .replace("‘", "'")
    )
    cleaned = " ".join(normalized.split())

    if len(cleaned) < MIN_NAME_LEN:
        return None, uz.NAME_TOO_SHORT
    if len(cleaned) > MAX_NAME_LEN:
        return None, uz.NAME_TOO_LONG

    parts = cleaned.split()
    if len(parts) == 1:
        return None, uz.ONE_WORD_NAME
    if len(parts) < 2:
        return None, uz.FULL_NAME_INVALID

    # Harflar, apostrof, nuqta va defis (masalan: A. Navoiy)
    name_pattern = re.compile(r"^[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ\'\.\-]+$")
    for part in parts:
        if not name_pattern.match(part) or len(part) < 2:
            return None, uz.FULL_NAME_INVALID

    first_name = parts[0].capitalize()
    last_name = " ".join(p.capitalize() for p in parts[1:])
    return (first_name, last_name), None


@router.callback_query(MenuCB.filter(F.action == "register"))
async def start_registration(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    await state.set_state(Registration.full_name)
    await safe_edit(callback, uz.ASK_FULL_NAME)


@router.message(Registration.full_name, F.text)
async def registration_full_name(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    names, error = _validate_full_name(message.text or "")
    if error or not names:
        await message.answer(error or uz.FULL_NAME_INVALID)
        return

    first_name, last_name = names
    user.first_name = first_name
    user.last_name = last_name
    user.phone = None
    user.is_registered = True

    await UserRepository(session).add_xp(user, 10)

    data = await state.get_data()
    pending = data.get("pending_payload")
    await state.clear()

    log.info("✅ Ro'yxatdan o'tdi: %s (%s)", user.telegram_id, user.full_name)
    await message.answer(uz.registered(user), reply_markup=ReplyKeyboardRemove())

    if pending:
        if await handle_payload(message, str(pending), user, session, state):
            return

    await show_main_menu(message, user, session)


@router.message(Registration.full_name)
async def registration_invalid_type(message: Message) -> None:
    """Foydalanuvchi matn o'rniga stiker, rasm yoki boshqa format yuborganda."""
    await message.answer(
        "⚠️ Iltimos, ism va familiyangizni <b>matn ko'rinishida</b> yozib yuboring.\n"
        "<i>Masalan: Anvar Karimov</i>"
    )



#  DIQQAT: ro'yxatdan o'tmaganlar uchun to'siq bu yerda EMAS.
#  U `IsRegistered` filtri orqali qo'yiladi (apps/bot/filters/) va
#  har bir router o'zi kerakligini belgilaydi. Bu yerda catch-all
#  handler qo'ysak, u qolgan routerlarni ham to'sib qo'yardi.
