"""
Testga javob berish.

Uch usul (raqobatchi botdagidek, lekin natijasi boyroq):

    1. Test raqamini yozish:     `12`
    2. Raqam va javoblar birga:  `12*abcdabcd`
    3. Tugma orqali

Oqim: raqam -> test kartochkasi + rasmlar -> javoblar -> natija.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import IsRegistered
from apps.bot.keyboards.callbacks import MenuCB, PageCB, TestCB
from apps.bot.keyboards.inline import (
    answering_keyboard,
    home_keyboard,
    notification_keyboard,
    personal_ranking_keyboard,
    profile_keyboard,
    result_keyboard,
    results_keyboard,
    simple_back_keyboard,
    test_card_keyboard,
)

from apps.bot.states import Answering
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit, send_media_group
from core.config import settings
from core.exceptions import TestLabError
from core.logging import get_logger
from modules.assessment.repository import AttemptRepository
from modules.assessment.service import AssessmentService
from modules.catalog.answer_key import split_test_number
from modules.catalog.models import Test
from modules.catalog.service import CatalogService
from modules.identity.models import User
from modules.identity.repository import UserRepository

log = get_logger(__name__)

router = Router(name="student_answer")
router.message.filter(IsRegistered())

PER_PAGE_RESULTS = 8
LEADERBOARD_SIZE = 10


# ======================================================================
#  TESTNI OCHISH
# ======================================================================

async def open_test(
    message: Message,
    test: Test,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """
    Testni ochadi: rasmlar, so'ng BITTA kartochka.

    TARTIB MUHIM
    ------------
    Ilgari kartochka rasmdan OLDIN, ko'rsatma esa KEYIN yuborilardi —
    rasm ikki xabar orasida qolib, ekran chalkash ko'rinardi.

    Endi: rasmlar birinchi, keyin bitta kartochka. Kartochka «javob
    berish» tugmasi bosilganda YANGI xabar yubormaydi — o'zi joyida
    ko'rsatmaga aylanadi. Chat toza qoladi.
    """
    catalog = CatalogService(session)
    assessment = AssessmentService(session)

    #  Javob bera oladimi? (allaqachon javob berganmi, ochiqmi)
    try:
        await assessment.ensure_can_answer(test, user)
    except TestLabError as error:
        await message.answer(
            f"⚠️ {error.user_text()}",
            reply_markup=home_keyboard(),
        )
        return

    await catalog.tests.increment_views(test)

    media = await catalog.list_media(test)

    #  Avval rasmlar — o'quvchi nima yechayotganini ko'rsin
    #  Anti-cheat: suv belgisi (watermark) va skrinshot/forward himoyasi bilan yuboriladi
    if media:
        await send_media_group(message, media, user=user, protect_content=True)

    #  Vaqt hisobi rasmlar YUBORILGACH boshlanadi — albom sekin yetib
    #  borsa, o'quvchi hali savolni ko'rmasidan vaqti ketib qolmasin.
    #  Vaqt chegarasi yo'q testda hech narsa yaratilmaydi.
    await assessment.begin(test, user)

    #  So'ng yagona kartochka: ma'lumot + tugma
    #
    #  Holat DARHOL o'rnatiladi — o'quvchi tugmani bosmasdan to'g'ridan-
    #  to'g'ri javoblarini yozsa ham qabul qilinishi kerak. Tugma esa
    #  "qanday yuboraman?" degan savolga javob beradi.
    await state.set_state(Answering.waiting)
    await state.update_data(test_id=test.id)

    await message.answer(
        uz.test_card(test, len(media)),
        reply_markup=test_card_keyboard(test.id, has_images=bool(media)),
        protect_content=True,
    )


async def show_result(
    message: Message,
    submit,
    session: AsyncSession,
    user: User,
) -> None:
    """
    Natijani ko'rsatadi.

    Ish `student/result.py` ga topshiriladi — u rasmli kartochka
    chizadi va sertifikat tugmasini qo'shadi.
    """
    from apps.bot.handlers.student.result import send_result

    await send_result(message, submit, user, session)


async def notify_author(
    message: Message,
    submit,
    student: User,
    session: AsyncSession,
) -> None:
    """
    Test muallifiga «yangi javob» xabarini yuboradi.

    Nega kerak? O'qituvchi testni e'lon qilgach jim qolardi — kimdir
    javob berganini bilish uchun o'zi kirib tekshirishi kerak edi.
    Bildirishnoma uni botga qaytaradi.

    Xato bo'lsa jim o'tamiz: o'quvchining natijasi muallifga xabar
    yetib bormagani uchun buzilmasligi kerak.
    """
    test = submit.test

    if test.author_id is None or test.author_id == student.id:
        return

    author = await UserRepository(session).get(test.author_id)

    if author is None or not author.notifications_enabled or author.is_banned:
        return

    try:
        await message.bot.send_message(
            author.telegram_id,
            uz.teacher_notification(submit, student),
            reply_markup=notification_keyboard(test.id),
        )
    except Exception as error:
        #  Muallif botni bloklagan bo'lishi mumkin — normal holat
        log.debug("Bildirishnoma yetkazilmadi (%s): %s", author.telegram_id, error)


async def notify_parents(
    message: Message,
    submit,
    student: User,
    session: AsyncSession,
) -> None:
    """Ota-ona yoki repetitorga avtomatik natija xabari yuborish."""
    parents = await UserRepository(session).get_parent_links(student.id)
    if not parents:
        return

    text = uz.parent_notification(submit, student)
    for link in parents:
        try:
            await message.bot.send_message(link.parent_telegram_id, text)
        except Exception as err:
            log.debug("Ota-onaga bildirishnoma yetkazilmadi (%s): %s", link.parent_telegram_id, err)



# ======================================================================
#  1-USUL — FAQAT RAQAM
# ======================================================================

@router.message(StateFilter(None, Answering.waiting), F.text.regexp(r"^\s*\d{1,6}\s*$"))
async def bare_number(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Foydalanuvchi shunchaki test raqamini yozdi: «12».

    `StateFilter(None, Answering.waiting)`: o'quvchi boshqa testni
    ochib qo'ygan bo'lsa ham, yangi raqam yuborganda yangi testga
    o'tishi kerak. Boshqa oqimlarni (admin qidiruvi) buzmaslik uchun
    faqat shu ikki holatda ushlanadi.
    """
    number = int((message.text or "").strip())

    catalog = CatalogService(session)
    test = await catalog.tests.get_by_number(number)

    if test is None:
        await message.answer(uz.TEST_NOT_FOUND, reply_markup=home_keyboard())
        return

    await open_test(message, test, user, session, state)


# ======================================================================
#  2-USUL — RAQAM VA JAVOBLAR BIRGA
# ======================================================================

@router.message(
    StateFilter(None, Answering.waiting),
    F.text.regexp(
        r"^\s*\d{1,6}(?:\s*[*xX×:]\s*[a-hA-HА-Яа-я0-9\s,.\-_]{1,400}|\s+[a-hA-HА-Яа-я\s,.\-_]{1,400})$"
    ),
)
async def one_shot(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Bir zumda javob berish: «12*abcdabcd».

    O'quvchi testni allaqachon ko'rgan bo'lsa (rasmlar guruhga
    tashlangan) — botga kirib bitta xabar bilan javob berib qo'yadi.
    """
    raw = message.text or ""
    number, _ = split_test_number(raw)

    if number is None:
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get_by_number(number)

    if test is None:
        await message.answer(uz.TEST_NOT_FOUND, reply_markup=home_keyboard())
        return

    assessment = AssessmentService(session)

    try:
        submit = await assessment.submit(test, user, raw)
    except TestLabError as error:
        await message.answer(
            f"⚠️ {error.user_text()}",
            reply_markup=home_keyboard(),
        )
        return

    await state.clear()
    await show_result(message, submit, session, user)
    await notify_author(message, submit, user, session)
    await notify_parents(message, submit, user, session)



# ======================================================================
#  3-USUL — TUGMA
# ======================================================================

@router.callback_query(MenuCB.filter(F.action == "answer"))
async def ask_code(callback: CallbackQuery, state: FSMContext) -> None:
    """«✅ Testga javob berish» tugmasi."""
    await safe_answer(callback)
    await state.clear()
    await safe_edit(
        callback,
        "🔑 <b>TEST KODINI KIRITING</b>\n"
        f"{uz.LINE}\n\n"
        "O'qituvchingiz bergan <b>test raqamini</b> yuboring.\n\n"
        "<i>Masalan: 12</i>",
        reply_markup=simple_back_keyboard(),
    )


@router.callback_query(TestCB.filter(F.action == "answer"))
async def answer_button(
    callback: CallbackQuery,
    callback_data: TestCB,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    «✅ Testga javob berish» tugmasi.

    Yangi xabar YUBORILMAYDI — kartochkaning o'zi ko'rsatmaga
    aylanadi. Shunday qilib ekranda bitta xabar qoladi.
    """
    await safe_answer(callback)

    if callback.message is None:
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)

    if test is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    assessment = AssessmentService(session)

    try:
        await assessment.ensure_can_answer(test, user)
    except TestLabError as error:
        await safe_answer(callback, error.user_text()[:200], alert=True)
        return

    media_count = await catalog.media_count(test)

    await state.set_state(Answering.waiting)
    await state.update_data(test_id=test.id)

    await safe_edit(
        callback,
        uz.ask_answers(test),
        reply_markup=answering_keyboard(test.id, has_images=media_count > 0),
    )


@router.callback_query(TestCB.filter(F.action == "open"))
async def back_to_card(
    callback: CallbackQuery,
    callback_data: TestCB,
    session: AsyncSession,
) -> None:
    """
    Ko'rsatmadan kartochkaga qaytish.

    Holat SAQLANADI — o'quvchi baribir javob yozsa qabul qilinaveradi.
    Bu tugma faqat ko'rinishni almashtiradi, oqimni bekor qilmaydi.
    """
    await safe_answer(callback)

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)

    if test is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    media_count = await catalog.media_count(test)

    await safe_edit(
        callback,
        uz.test_card(test, media_count),
        reply_markup=test_card_keyboard(test.id, has_images=media_count > 0),
    )


@router.callback_query(TestCB.filter(F.action == "webapp_info"))
async def webapp_info_handler(
    callback: CallbackQuery,
    callback_data: TestCB,
) -> None:
    """Lokal rejimda Mini App havolasi va yo'riqnoma."""
    await safe_answer(callback)
    if callback.message is None:
        return

    if not settings.webapp.enabled:
        await callback.message.answer(
            "⚠️ Hozirda Mini App administrator tomonidan vaqtincha to'xtatilgan.\n\n"
            "Siz testni to'g'ridan-to'g'ri bot orqali («✅ Testga javob berish» tugmasi yoki raqam bilan) yechishingiz mumkin.",
            parse_mode="HTML",
        )
        return
    url = f"{settings.webapp.base_url}/test/{callback_data.test_id}"
    await callback.message.answer(
        f"📱 <b>Ekranda yechish (Mini App)</b>\n\n"
        f"Telegram ichidagi Mini App (Web App) oynasi ko'tarilishi uchun Telegram faqat xavfsiz <b>HTTPS</b> havolalarni qabul qiladi.\n\n"
        f"💻 <b>Lokal brauzerda ochish uchun:</b>\n"
        f"{url}\n\n"
        f"🌐 <i>Eslatma: Bot internetga ulangan paytda avtomatik Cloudflare HTTPS tunneli orqali Telegram ichida to'g'ridan-to'g'ri Mini App oynasi ochiladi.</i>",
        parse_mode="HTML",
    )


# ======================================================================
#  JAVOBLARNI QABUL QILISH
# ======================================================================

@router.message(Answering.waiting, F.text)
async def receive_answers(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """O'quvchi javoblarini yubordi."""
    data = await state.get_data()
    test_id = data.get("test_id")

    if not test_id:
        await state.clear()
        await message.answer(uz.SESSION_EXPIRED, reply_markup=home_keyboard())
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(int(test_id))

    if test is None:
        await state.clear()
        await message.answer(uz.TEST_NOT_FOUND, reply_markup=home_keyboard())
        return

    assessment = AssessmentService(session)

    try:
        submit = await assessment.submit(test, user, message.text or "")
    except TestLabError as error:
        #  Holatni TOZALAMAYMIZ — o'quvchi qayta urinib ko'rsin.
        #  Xato matni allaqachon nima noto'g'ri ekanini tushuntiradi.
        media_count = await catalog.media_count(test)
        await message.answer(
            f"⚠️ {error.user_text()}",
            reply_markup=answering_keyboard(test.id, has_images=media_count > 0),
        )
        return

    await state.clear()
    await show_result(message, submit, session, user)
    await notify_author(message, submit, user, session)
    await notify_parents(message, submit, user, session)


@router.message(F.web_app_data)
async def receive_webapp_answers(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Telegram Mini App orqali yuborilgan javoblar."""
    raw = (message.web_app_data.data or "").strip()
    data = await state.get_data()
    test_id = data.get("test_id")

    catalog = CatalogService(session)
    test = None

    if "*" in raw or ":" in raw:
        num_str, key_str = split_test_number(raw)
        if num_str is not None:
            test = await catalog.tests.get_by_number(num_str)
            raw = key_str

    if test is None and test_id:
        test = await catalog.tests.get_full(int(test_id))

    if test is None:
        await message.answer(uz.TEST_NOT_FOUND, reply_markup=home_keyboard())
        return

    assessment = AssessmentService(session)
    try:
        submit = await assessment.submit(test, user, raw)
    except TestLabError as error:
        await message.answer(f"⚠️ {error.user_text()}")
        return

    await state.clear()
    await show_result(message, submit, session, user)
    await notify_author(message, submit, user, session)
    await notify_parents(message, submit, user, session)



@router.message(Answering.waiting)
async def wrong_answer_type(message: Message) -> None:
    await message.answer(
        "⚠️ Javoblaringizni <b>matn</b> ko'rinishida yuboring.\n\n"
        "<i>Masalan: abcdabcd</i>"
    )


# ======================================================================
#  NATIJALARIM
# ======================================================================

async def _render_results(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    page_number: int,
) -> None:
    page = await AttemptRepository(session).list_by_user(
        user.id, page=page_number, per_page=PER_PAGE_RESULTS
    )
    await safe_edit(callback, uz.my_results(page), reply_markup=results_keyboard(page))


@router.callback_query(MenuCB.filter(F.action == "results"))
async def open_results(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)
    await _render_results(callback, user, session, 1)


@router.callback_query(PageCB.filter(F.scope == "results"))
async def page_results(
    callback: CallbackQuery,
    callback_data: PageCB,
    user: User,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)
    await _render_results(callback, user, session, callback_data.page)


# ======================================================================
#  REYTING VA PROFIL
# ======================================================================

@router.callback_query(MenuCB.filter(F.action == "board"))
async def open_leaderboard(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)

    users = UserRepository(session)
    rank = await users.xp_rank(user)
    total_users = await users.count_leaderboard_users()
    stats = await AttemptRepository(session).user_stats(user.id)

    await safe_edit(
        callback,
        uz.personal_ranking(user, rank, total_users, stats),
        reply_markup=personal_ranking_keyboard(),
    )



@router.callback_query(MenuCB.filter(F.action == "profile"))
async def open_profile(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)

    stats = await AttemptRepository(session).user_stats(user.id)
    rank = await UserRepository(session).xp_rank(user)

    await safe_edit(
        callback,
        uz.profile(user, stats, rank),
        reply_markup=profile_keyboard(),
    )



@router.message(Command("profile"))
async def cmd_profile(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    stats = await AttemptRepository(session).user_stats(user.id)
    rank = await UserRepository(session).xp_rank(user)
    await message.answer(uz.profile(user, stats, rank), reply_markup=profile_keyboard())

