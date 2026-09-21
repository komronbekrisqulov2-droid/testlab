"""/start, ro'yxatdan o'tish va bosh menyu."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
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

#  Telefon: +998901112233, 998901112233, 901112233
PHONE_PATTERN = re.compile(r"^\+?\d{7,15}$")

MIN_NAME = 2
MAX_NAME = 60


def phone_keyboard() -> ReplyKeyboardMarkup:
    """Telefon so'rash uchun pastki klaviatura."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=uz.BTN_SHARE_PHONE, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="yoki qo'lda yozing",
    )


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

@router.callback_query(MenuCB.filter(F.action == "register"))
async def start_registration(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    await state.set_state(Registration.first_name)
    await safe_edit(callback, uz.ASK_FIRST_NAME)


def _validate_name(raw: str) -> tuple[str | None, str | None]:
    """
    Ismni tekshiradi.

    Returns:
        (tozalangan_ism, xato_matni) — bittasi doim None.
    """
    name = " ".join((raw or "").split())

    if len(name) < MIN_NAME:
        return None, uz.NAME_TOO_SHORT
    if len(name) > MAX_NAME:
        return None, uz.NAME_TOO_LONG

    return name, None


@router.message(Registration.first_name, F.text)
async def registration_first_name(message: Message, state: FSMContext) -> None:
    name, error = _validate_name(message.text or "")

    if error:
        await message.answer(error)
        return

    await state.update_data(first_name=name)
    await state.set_state(Registration.last_name)
    await message.answer(uz.ASK_LAST_NAME)


@router.message(Registration.last_name, F.text)
async def registration_last_name(message: Message, state: FSMContext) -> None:
    name, error = _validate_name(message.text or "")

    if error:
        await message.answer(error)
        return

    await state.update_data(last_name=name)
    await state.set_state(Registration.phone)
    await message.answer(uz.ASK_PHONE, reply_markup=phone_keyboard())


@router.message(Registration.phone, F.contact)
async def registration_phone_contact(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Tugma orqali yuborilgan raqam."""
    await _finish_registration(
        message, state, user, session, phone=message.contact.phone_number
    )


@router.message(Registration.phone, F.text)
async def registration_phone_text(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Qo'lda yozilgan raqam."""
    raw = (message.text or "").strip()

    #  «O'tkazib yuborish» — telefon ixtiyoriy
    if raw.lower() in {"/skip", uz.BTN_SKIP.lower(), "o'tkazish", "otkazish"}:
        await _finish_registration(message, state, user, session, phone=None)
        return

    digits = re.sub(r"[^\d+]", "", raw)

    if not PHONE_PATTERN.match(digits):
        await message.answer(
            "⚠️ Raqam noto'g'ri.\n\n"
            "Namuna: <code>+998901112233</code>\n\n"
            "<i>Yoki pastdagi tugmani bosing.</i>"
        )
        return

    await _finish_registration(message, state, user, session, phone=digits)


@router.message(Registration.phone)
async def registration_phone_other(message: Message) -> None:
    await message.answer(
        "⚠️ Telefon raqamini yuboring yoki pastdagi tugmani bosing."
    )


async def _finish_registration(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    *,
    phone: str | None,
) -> None:
    """Ro'yxatdan o'tishni yakunlaydi."""
    data = await state.get_data()

    user.first_name = data.get("first_name") or user.first_name
    user.last_name = data.get("last_name") or user.last_name
    user.phone = phone
    user.is_registered = True

    await UserRepository(session).add_xp(user, 10)
    await state.clear()

    log.info("✅ Ro'yxatdan o'tdi: %s (%s)", user.telegram_id, user.full_name)

    await message.answer(uz.registered(user), reply_markup=ReplyKeyboardRemove())

    #  Havola orqali kelgan bo'lsa — o'sha joyga olib boramiz.
    #  Aks holda o'quvchi posterdagi tugmani bosib, ro'yxatdan o'tib,
    #  keyin testni qo'lda qidirishga majbur bo'lardi.
    pending = data.get("pending_payload")
    if pending:
        await state.clear()
        if await handle_payload(message, str(pending), user, session, state):
            return

    await show_main_menu(message, user, session)


#  DIQQAT: ro'yxatdan o'tmaganlar uchun to'siq bu yerda EMAS.
#  U `IsRegistered` filtri orqali qo'yiladi (apps/bot/filters/) va
#  har bir router o'zi kerakligini belgilaydi. Bu yerda catch-all
#  handler qo'ysak, u qolgan routerlarni ham to'sib qo'yardi.
