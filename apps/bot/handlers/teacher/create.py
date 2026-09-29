"""
Test yaratish.

Ikki usul:

    1. BITTA XABARDA — `Matematika+abcdabcd`
       Eng tez. Foydalanuvchi hech qanday tugma bosmaydi.

    2. RASM BILAN — «➕ Test yaratish» → rasm → kalit
       Savol matni yozilmaydi, varaqa surati yuboriladi.

Ikkalasida ham savollar soni ALOHIDA so'ralmaydi: kalit uzunligining
o'zi uni aytadi (25 harf = 25 savol).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import HasPermission, IsRegistered
from apps.bot.keyboards.callbacks import BuildCB, MenuCB
from apps.bot.keyboards.inline import (
    building_keyboard,
    home_keyboard,
    published_keyboard,
    simple_back_keyboard,
)
from apps.bot.states import Building
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.config import settings
from core.exceptions import TestLabError
from core.logging import get_logger
from core.security.permissions import Permission
from modules.catalog.answer_key import TITLE_SEPARATOR
from modules.catalog.models import Test
from modules.catalog.service import CatalogService
from modules.identity.models import User
from modules.media import poster

log = get_logger(__name__)

router = Router(name="teacher_create")
router.message.filter(IsRegistered(), HasPermission(Permission.TEST_CREATE))
router.callback_query.filter(HasPermission(Permission.TEST_CREATE))

#  Rasm va hujjat sifatida qabul qilinadigan kengaytmalar va MIME turlari
ALLOWED_DOC_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt",
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic",
})

ALLOWED_MIME_PREFIXES: tuple[str, ...] = (
    "image/",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-word",
    "application/x-msword",
    "application/x-docx",
    "application/rtf",
    "text/plain",
)


def _is_allowed_document(document) -> bool:
    mime = (document.mime_type or "").lower()
    file_name = (document.file_name or "").lower()

    if any(mime.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES):
        return True

    if any(file_name.endswith(ext) for ext in ALLOWED_DOC_EXTENSIONS):
        return True

    return False


# ======================================================================
#  YORDAMCHILAR
# ======================================================================

async def _load_draft(
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> Test | None:
    """FSM'dagi qoralamani yuklaydi va egaligini tekshiradi."""
    data = await state.get_data()
    test_id = data.get("draft_id")

    if not test_id:
        return None

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(int(test_id))

    if test is None:
        return None
    if test.author_id != user.id and not user.is_admin:
        return None

    return test


async def _publish_and_show(
    message: Message,
    session: AsyncSession,
    test: Test,
) -> None:
    """
    E'lon qilingan testni ko'rsatadi: reklama posteri + ulashish xabari.

    Poster guruhga uzatilganda oddiy xabar emas, **e'lon** kabi
    ko'rinadi — bu o'qituvchining o'z reklamasi.
    """
    catalog = CatalogService(session)
    media_count = await catalog.media_count(test)

    caption = uz.test_published(test, settings.bot.username, media_count)
    keyboard = published_keyboard(test)

    poster_bytes = _render_poster(test)

    if poster_bytes is None:
        #  Poster chizilmadi — matn baribir yuboriladi
        await message.answer(caption, reply_markup=keyboard)
        return

    #  Telegram rasm izohi 1024 belgi bilan cheklangan
    if len(caption) <= 1024:
        await message.answer_photo(
            photo=BufferedInputFile(poster_bytes, filename=f"test_{test.number}.png"),
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await message.answer_photo(
            photo=BufferedInputFile(poster_bytes, filename=f"test_{test.number}.png"),
        )
        await message.answer(caption, reply_markup=keyboard)


def _render_poster(test: Test) -> bytes | None:
    """Posterni chizadi. Xato bo'lsa None (test baribir e'lon qilingan)."""
    try:
        return poster.render(poster.PosterData(
            test_title=test.title,
            test_number=test.number,
            questions_count=test.questions_count,
            author_name=test.author_name,
            category=test.category.name if test.category else None,
            time_limit_min=test.time_limit_sec // 60,
            pass_score=test.pass_score,
            deep_link=settings.bot.deep_link(f"t{test.number}"),
        ))
    except Exception as error:
        log.exception("Poster chizilmadi: %s", error)
        return None


# ======================================================================
#  1-USUL — BITTA XABARDA
# ======================================================================

@router.message(
    StateFilter(None),
    F.text.contains(TITLE_SEPARATOR),
    ~F.text.startswith("/"),
)
async def create_one_line(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    """
    `Matematika+abcdabcd` — bitta xabarda test.

    Filtr `+` belgisiga qaraydi. Oddiy matnda `+` kam uchraydi, lekin
    uchrasa ham xato matni aniq bo'ladi va foydalanuvchi chalkashmaydi.
    """
    catalog = CatalogService(session)

    try:
        await catalog.ensure_within_limit(user)
        test = await catalog.create_from_one_line(user, message.text or "")
    except TestLabError as error:
        await message.answer(f"⚠️ {error.user_text()}")
        return

    await _publish_and_show(message, session, test)


# ======================================================================
#  2-USUL — RASM BILAN
# ======================================================================

@router.callback_query(MenuCB.filter(F.action == "create"))
async def start_building(callback: CallbackQuery, state: FSMContext) -> None:
    """«➕ Test yaratish» tugmasi."""
    await safe_answer(callback)
    await state.clear()
    await state.set_state(Building.active)
    await safe_edit(callback, uz.CREATE_START, reply_markup=simple_back_keyboard())


@router.message(Command("new"))
async def start_building_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Building.active)
    await message.answer(uz.CREATE_START, reply_markup=simple_back_keyboard())


_user_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _get_user_lock(user_id: int) -> asyncio.Lock:
    """Foydalanuvchi uchun lock qaytaradi va xotira to'lib ketishini oldini oladi."""
    if len(_user_locks) > 200:
        for uid in list(_user_locks.keys()):
            lock = _user_locks.get(uid)
            if lock and not lock.locked():
                _user_locks.pop(uid, None)
    return _user_locks[user_id]


async def _add_photo(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    *,
    file_id: str,
    file_unique_id: str | None,
    media_type: str,
    caption: str | None,
) -> None:
    """Rasmni qo'shadi va tasdiq yuboradi (albom poygasidan himoyalangan)."""
    catalog = CatalogService(session)

    async with _get_user_lock(user.id):
        test = await _load_draft(session, state, user)

        #  Test aynan BIRINCHI RASM kelganda yaratiladi — foydalanuvchi
        #  tugmani bosib fikridan qaytsa bazada axlat qolmaydi
        if test is None:
            try:
                await catalog.ensure_within_limit(user)
                test = await catalog.create_draft(user, title=caption)
            except TestLabError as error:
                await message.answer(f"⚠️ {error.user_text()}")
                return

            await state.update_data(draft_id=test.id)

        try:
            added = await catalog.add_media(
                test,
                user,
                file_id=file_id,
                file_unique_id=file_unique_id,
                media_type=media_type,
                caption=None,
            )
        except TestLabError as error:
            await message.answer(f"⚠️ {error.user_text()}")
            return

        if added is None:
            await message.answer(uz.PHOTO_DUPLICATE)
            return

        total = await catalog.media_count(test)

        data = await state.get_data()
        status_msg_id = data.get("media_status_msg_id")

        text = uz.photo_added(total)
        kb = building_keyboard(test.id, has_photo=True)

        #  Albom yuborilganda xabarni tahrirlaymiz, chat to'lib ketmasin
        if message.media_group_id and status_msg_id:
            try:
                await message.bot.edit_message_text(
                    text=text,
                    chat_id=message.chat.id,
                    message_id=status_msg_id,
                    reply_markup=kb,
                )
                return
            except Exception:
                pass

        sent = await message.answer(text, reply_markup=kb)
        await state.update_data(media_status_msg_id=sent.message_id)


@router.message(Building.active, F.photo)
async def building_photo(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Test varaqasi rasmi.

    Telegram bir nechta o'lchamdagi nusxani yuboradi — eng kattasini
    (`photo[-1]`) olamiz, sifat yo'qolmasligi uchun.
    """
    photo = message.photo[-1]
    await _add_photo(
        message, state, user, session,
        file_id=photo.file_id,
        file_unique_id=photo.file_unique_id,
        media_type="photo",
        caption=message.caption,
    )


@router.message(Building.active, F.document)
async def building_document(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Rasm, PDF yoki Word (.doc, .docx) fayli yuborilganda qabul qiladi.
    """
    document = message.document

    if not _is_allowed_document(document):
        await message.answer(uz.NOT_A_PHOTO)
        return

    await _add_photo(
        message, state, user, session,
        file_id=document.file_id,
        file_unique_id=document.file_unique_id,
        media_type="document",
        caption=message.caption,
    )


@router.message(Building.active, F.text, ~F.text.startswith("/"))
async def building_key(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Matn keldi — bu javoblar kaliti.

    Kalit qabul qilinishi bilan test AVTOMATIK e'lon qilinadi. Alohida
    «e'lon qilish» tugmasi qo'yilmadi: u hech qanday tanlov bermaydi,
    faqat bitta bosishni qo'shadi.
    """
    test = await _load_draft(session, state, user)

    if test is None:
        await message.answer(uz.NO_PHOTO_YET)
        return

    catalog = CatalogService(session)

    try:
        await catalog.set_answer_key(test, user, message.text or "")
        await catalog.publish(test, user)
    except TestLabError as error:
        #  Holatni TOZALAMAYMIZ — o'qituvchi qayta urinib ko'rsin
        await message.answer(
            f"⚠️ {error.user_text()}",
            reply_markup=building_keyboard(test.id, has_photo=True),
        )
        return

    await state.clear()
    await _publish_and_show(message, session, test)


@router.message(Building.active)
async def building_wrong_type(message: Message) -> None:
    """Stiker, video, ovozli xabar va h.k."""
    await message.answer(uz.NOT_A_PHOTO)


# ======================================================================
#  TUGMALAR
# ======================================================================

@router.callback_query(BuildCB.filter(F.action == "undo_photo"))
async def undo_photo(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Oxirgi rasmni o'chirish."""
    await safe_answer(callback)

    test = await _load_draft(session, state, user)
    if test is None:
        await safe_edit(callback, uz.SESSION_EXPIRED, reply_markup=home_keyboard())
        await state.clear()
        return

    catalog = CatalogService(session)
    removed = await catalog.remove_last_media(test, user)

    if not removed:
        await safe_answer(callback, "O'chiriladigan rasm yo'q")
        return

    total = await catalog.media_count(test)

    await safe_edit(
        callback,
        uz.photo_added(total) if total else uz.CREATE_START,
        reply_markup=building_keyboard(test.id, has_photo=total > 0),
    )


@router.callback_query(BuildCB.filter(F.action == "cancel"))
async def cancel_building(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Yaratishni bekor qilish.

    Qoralama BUTUNLAY o'chiriladi — yarim yaratilgan testlar «Mening
    testlarim» ro'yxatini axlatga to'ldirmasligi kerak. Rasmlar kaskad
    orqali o'zi ketadi.
    """
    await safe_answer(callback)

    test = await _load_draft(session, state, user)

    if test is not None and test.is_draft:
        await CatalogService(session).delete(test, user)

    await state.clear()
    await safe_edit(callback, uz.CANCELLED, reply_markup=home_keyboard())
