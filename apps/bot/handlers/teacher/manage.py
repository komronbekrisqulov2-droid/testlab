"""Mening testlarim: ro'yxat, boshqaruv, javob berganlar, Excel."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import HasPermission, IsRegistered  # noqa: F401
from apps.bot.keyboards.callbacks import AdminCB, MenuCB, PageCB, PeopleCB, TestCB
from apps.bot.keyboards.inline import (
    analysis_keyboard,
    back_button,
    confirm_delete_keyboard,
    home_button,
    my_tests_keyboard,
    participants_keyboard,
    test_edit_keyboard,
    test_group_select_keyboard,
    test_manage_keyboard,
    test_random_keyboard,
    timer_select_keyboard,
)
import urllib.parse

from apps.bot.states import ChannelShare, RandomQuestionsCount, TestEdit, TestSchedule
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit, send_media_group
from core.config import settings
from core.datetime_utils import fmt_datetime, parse_datetime_input, utcnow
from core.exceptions import TestLabError
from core.logging import get_logger
from core.security.permissions import Permission
from infrastructure.database.repository import Page
from modules.assessment.repository import AttemptRepository
from modules.assessment.service import AssessmentService
from modules.catalog.models import Test
from modules.catalog.service import CatalogService
from modules.identity.models import User

log = get_logger(__name__)

router = Router(name="teacher_manage")
router.message.filter(IsRegistered())

#  Huquqi yo'qlar bu routerdan chetlab o'tadi va `access` routeriga
#  tushadi — u yerda "Tushunmadim" emas, chiroyli tushuntirish beriladi.
router.callback_query.filter(HasPermission(Permission.TEST_CREATE))

PER_PAGE_TESTS = 8
PER_PAGE_PEOPLE = 10

#  Telegram hujjat chegarasi 50 MB — biz undan ancha pastdamiz,
#  lekin har ehtimolga qarshi tekshiramiz
MAX_DOCUMENT_BYTES = 45 * 1024 * 1024


async def _load_owned(
    session: AsyncSession,
    test_id: int,
    user: User,
) -> Test | None:
    """
    Testni yuklaydi va ko'rish huquqini tekshiradi.

    Muallif o'z testini, admin barchasini ko'ra oladi.
    """
    test = await CatalogService(session).tests.get_full(test_id)

    if test is None:
        return None
    if test.author_id == user.id:
        return test
    if user.can(Permission.RESULTS_VIEW_ANY):
        return test

    return None


# ======================================================================
#  MENING TESTLARIM
# ======================================================================

async def _render_my_tests(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    page_number: int,
) -> None:
    catalog = CatalogService(session)
    page = await catalog.tests.list_by_author(
        user.id, page=page_number, per_page=PER_PAGE_TESTS
    )
    await safe_edit(
        callback,
        uz.my_tests_page(page, page.total),
        reply_markup=my_tests_keyboard(page),
    )


@router.callback_query(MenuCB.filter(F.action == "mytests"))
async def open_my_tests(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    #  Huquq tekshiruvi router filtrida — bu yerda takrorlanmaydi
    await safe_answer(callback)
    await _render_my_tests(callback, user, session, 1)


@router.callback_query(PageCB.filter(F.scope == "mytests"))
async def page_my_tests(
    callback: CallbackQuery,
    callback_data: PageCB,
    user: User,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)
    await _render_my_tests(callback, user, session, callback_data.page)


# ======================================================================
#  TESTNI BOSHQARISH
# ======================================================================

@router.callback_query(TestCB.filter(F.action == "manage"))
async def manage_test(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    if state:
        await state.clear()
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    catalog = CatalogService(session)
    media_count = await catalog.media_count(test)
    participants = await AttemptRepository(session).count_finished_by_test(test.id)

    await safe_edit(
        callback,
        uz.test_manage(test, media_count, participants),
        reply_markup=test_manage_keyboard(test),
    )


@router.callback_query(TestCB.filter(F.action.in_({"publish", "archive"})))
async def change_status(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Testni e'lon qilish yoki arxivlash."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    catalog = CatalogService(session)

    try:
        if callback_data.action == "publish":
            await catalog.publish(test, user)
            await safe_answer(callback, "🟢 E'lon qilindi")
        else:
            await catalog.archive(test, user)
            await safe_answer(callback, "📦 Arxivlandi")
    except TestLabError as error:
        await safe_answer(callback, error.user_text()[:200], alert=True)
        return

    await manage_test(callback, callback_data, user, session)


@router.callback_query(TestCB.filter(F.action == "timer_menu"))
async def open_timer_menu(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Taymer, holat va jadval sozlamalari menyusi."""
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    curr_text = f"{test.time_limit_sec // 60} daqiqa" if test.time_limit_sec > 0 else "Cheksiz (Vaqtsiz)"
    status_icon = "🟢 Ochiq (Faol)" if test.is_published else "🔴 Yopiq (Qulflangan)"
    start_info = fmt_datetime(test.starts_at) if test.starts_at else "Belgilanmagan (Darhol ochiq)"
    end_info = fmt_datetime(test.ends_at) if test.ends_at else "Belgilanmagan (Muddatsiz)"

    text = (
        f"⏱ <b>TEST TAYMERI VA KIRISH SOZLAMALARI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Test: <b>{uz.escape(test.title)}</b> (№{test.number})\n"
        f"📌 Holat: <b>{status_icon}</b>\n"
        f"⏱ Har bir urinish vaqti: <b>{curr_text}</b>\n"
        f"📅 Avtomatik ochilish: <b>{start_info}</b>\n"
        f"🏁 Avtomatik yopilish: <b>{end_info}</b>\n\n"
        f"<i>Quyidagi tugmalar orqali testni ixtiyoriy paytda ochib/yopishingiz yoki avtomatik jadval va taymer belgilashingiz mumkin:</i>"
    )
    await safe_edit(
        callback,
        text,
        reply_markup=timer_select_keyboard(test),
    )


@router.callback_query(TestCB.filter(F.action == "toggle_status"))
async def toggle_test_status(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Testni zudlik bilan ochish yoki yopish."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    catalog = CatalogService(session)
    if test.is_published:
        await catalog.tests.archive(test)
        await safe_answer(callback, "🔴 Test yopildi (qulflandi). O'quvchilar yechishi to'xtatildi.", alert=True)
    else:
        await catalog.tests.publish(test)
        await safe_answer(callback, "🟢 Test ochildi (faollashtirildi). Endi yechish mumkin!", alert=True)

    await open_timer_menu(callback, callback_data, user, session)


# ======================================================================
#  RANDOMIZATSIYA (KO'CHIRISHGA QARSHI)
# ======================================================================

@router.callback_query(TestCB.filter(F.action == "random_menu"))
async def open_random_menu(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Randomizatsiya sozlamalari ekrani."""
    await safe_answer(callback)
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    status_str = "🟢 Yoqilgan (Faol)" if test.is_randomized else "⚪ O'chirilgan"
    count_str = f"{test.random_questions_count} ta savol" if test.random_questions_count else "Barcha savollar (Aralashgan)"
    total_q = test.questions_count or len(test.key_letters)

    text = (
        f"🎲 <b>SAVOLLARNI RANDOM QILISH (KO'CHIRISHGA QARSHI)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Test: <b>{uz.escape(test.title)}</b> (№{test.number})\n"
        f"📊 Umumiy savollar: <b>{total_q} ta</b>\n"
        f"📌 Random holati: <b>{status_str}</b>\n"
        f"🔢 O'quvchiga tushish soni: <b>{count_str}</b>\n\n"
        f"💡 <i>Randomizatsiya yoqilganda har bir o'quvchi testni ochganida unga savollar "
        f"mutlaqo tasodifiy tartibda yoki tasodifiy tanlangan N ta savol tushadi. "
        f"Bu o'quvchilar bir-biridan ko'chirib olishini butunlay (0 ga) yo'q qiladi!</i>"
    )
    await safe_edit(
        callback,
        text,
        reply_markup=test_random_keyboard(test),
    )


@router.callback_query(TestCB.filter(F.action == "toggle_random"))
async def toggle_random(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Randomizatsiyani yoqish yoki o'chirish."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    test.is_randomized = not test.is_randomized
    await session.commit()
    msg = "🟢 Randomizatsiya yoqildi!" if test.is_randomized else "🔴 Randomizatsiya o'chirildi."
    await safe_answer(callback, msg)
    await open_random_menu(callback, callback_data, user, session)


@router.callback_query(TestCB.filter(F.action == "set_rand_all"))
async def set_random_all(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Barcha savollarni aralashtirib berish rejimiga o'tish."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    test.random_questions_count = None
    test.is_randomized = True
    await session.commit()
    await safe_answer(callback, "♾ Endi barcha savollar aralashtiriladi!")
    await open_random_menu(callback, callback_data, user, session)


@router.callback_query(TestCB.filter(F.action == "set_rand_count"))
async def prompt_random_count(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    state: FSMContext,
) -> None:
    """O'quvchiga nechta savol tushishini so'rash."""
    await safe_answer(callback)
    await state.set_state(RandomQuestionsCount.count)
    await state.update_data(random_test_id=callback_data.test_id)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=uz.BTN_CANCEL,
                    callback_data=TestCB(action="random_menu", test_id=callback_data.test_id).pack(),
                )
            ]
        ]
    )
    await safe_edit(
        callback,
        "🔢 <b>Har bir o'quvchiga nechta savol tushsin?</b>\n\n"
        "Masalan, testda 50 ta savol bo'lsa, har bir o'quvchiga shulardan tasodifiy <b>20</b> tasi "
        "tushishi uchun <code>20</code> deb yozib yuboring:",
        reply_markup=cancel_kb,
    )


@router.message(StateFilter(RandomQuestionsCount.count))
async def save_random_count(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Kiritilgan savollar sonini saqlash."""
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("⚠️ Iltimos, faqat musbat raqam kiriting (masalan: 20).")
        return

    count = int(raw)
    data = await state.get_data()
    test_id = data.get("random_test_id")
    await state.clear()

    test = await _load_owned(session, test_id, user)
    if test is None:
        await message.answer("⚠️ Test topilmadi.")
        return

    total_q = test.questions_count or len(test.key_letters)
    if count < 1 or count > total_q:
        await message.answer(
            f"⚠️ Savollar soni 1 dan {total_q} gacha bo'lishi kerak.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Random sozlamalariga",
                            callback_data=TestCB(action="random_menu", test_id=test.id).pack(),
                        )
                    ]
                ]
            ),
        )
        return

    test.random_questions_count = count
    test.is_randomized = True
    await session.commit()

    await message.answer(
        f"✅ <b>Sozlama saqlandi!</b>\n\n"
        f"Har bir o'quvchiga umumiy {total_q} ta savoldan tasodifiy <b>{count} tasi</b> tanlab beriladi.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Testni boshqarish",
                        callback_data=TestCB(action="manage", test_id=test.id).pack(),
                    )
                ]
            ]
        ),
    )


# ======================================================================
#  GURUH / SINFGA BIRIKTIRISH
# ======================================================================

@router.callback_query(TestCB.filter(F.action == "group_menu"))
async def open_group_menu(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Testni guruhga biriktirish menyusi."""
    await safe_answer(callback)
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    from modules.classroom.repository import ClassroomRepository
    cls_repo = ClassroomRepository(session)
    classrooms = await cls_repo.list_by_teacher(user.id)

    curr_group = test.classroom.name if (test.classroom_id and test.classroom) else "🌐 Barchaga ochiq (Umumiy)"

    text = (
        f"👥 <b>TESTNI GURUHGA BIRIKTIRISH</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Test: <b>{uz.escape(test.title)}</b> (№{test.number})\n"
        f"🔒 Hozirgi biriktirilgan guruh: <b>{curr_group}</b>\n\n"
        f"<i>Agar ma'lum bir guruhni tanlasangiz, bu test yopiq bo'ladi va faqat "
        f"o'sha guruh a'zolari uni yecha oladi. Boshqa o'quvchilar kira olmaydi.</i>\n\n"
        f"Guruhni tanlang:"
    )
    await safe_edit(
        callback,
        text,
        reply_markup=test_group_select_keyboard(test, classrooms),
    )


@router.callback_query(TestCB.filter(F.action == "set_group"))
async def set_test_group(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Testni tanlangan guruhga biriktirish yoki barchaga ochish."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    if callback_data.value == 0:
        test.classroom_id = None
        await session.commit()
        await safe_answer(callback, "🌐 Test endi barchaga ochiq!")
    else:
        from modules.classroom.repository import ClassroomRepository
        cls_repo = ClassroomRepository(session)
        target_cls = await cls_repo.get(callback_data.value)
        if target_cls and target_cls.teacher_id == user.id:
            test.classroom_id = target_cls.id
            await session.commit()
            await safe_answer(callback, f"🔒 Test «{target_cls.name}» guruhiga biriktirildi!")

    await open_group_menu(callback, callback_data, user, session)


@router.callback_query(TestCB.filter(F.action == "sched_start"))
async def start_schedule_start(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    state: FSMContext,
) -> None:
    """Ochilish vaqtini so'rash."""
    await safe_answer(callback)
    await state.set_state(TestSchedule.start_time)
    await state.update_data(schedule_test_id=callback_data.test_id)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=uz.BTN_CANCEL,
                    callback_data=TestCB(action="timer_menu", test_id=callback_data.test_id).pack(),
                )
            ]
        ]
    )
    if callback.message:
        await callback.message.answer(
            "📅 <b>Test ochilish vaqtini kiriting:</b>\n\n"
            "Formatlar:\n"
            "• Bugun uchun: <code>14:30</code>\n"
            "• Sana bilan: <code>22.09 14:30</code> yoki <code>22.09.2026 14:30</code>\n\n"
            "<i>Bekor qilish uchun /cancel yuboring.</i>",
            reply_markup=cancel_kb,
        )


@router.callback_query(TestCB.filter(F.action == "sched_end"))
async def start_schedule_end(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    state: FSMContext,
) -> None:
    """Yopilish vaqtini so'rash."""
    await safe_answer(callback)
    await state.set_state(TestSchedule.end_time)
    await state.update_data(schedule_test_id=callback_data.test_id)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=uz.BTN_CANCEL,
                    callback_data=TestCB(action="timer_menu", test_id=callback_data.test_id).pack(),
                )
            ]
        ]
    )
    if callback.message:
        await callback.message.answer(
            "🏁 <b>Test yopilish vaqtini kiriting:</b>\n\n"
            "Formatlar:\n"
            "• Bugun uchun: <code>21:00</code>\n"
            "• Sana bilan: <code>22.09 21:00</code> yoki <code>22.09.2026 21:00</code>\n\n"
            "<i>Bekor qilish uchun /cancel yuboring.</i>",
            reply_markup=cancel_kb,
        )


@router.callback_query(TestCB.filter(F.action == "clear_sched"))
async def clear_schedule(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Jadval vaqtlarini tozalash."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    catalog = CatalogService(session)
    await catalog.tests.update_fields(test, starts_at=None, ends_at=None)
    await safe_answer(callback, "✅ Jadval vaqtlari tozalandi", alert=True)
    await open_timer_menu(callback, callback_data, user, session)


@router.message(TestSchedule.start_time, F.text)
async def process_schedule_start(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Ochilish vaqtini saqlash."""
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("✖️ Bekor qilindi.")
        return

    data = await state.get_data()
    test_id = data.get("schedule_test_id")
    if not test_id:
        await state.clear()
        return

    test = await _load_owned(session, test_id, user)
    if test is None:
        await state.clear()
        await message.answer(uz.NO_PERMISSION)
        return

    parsed_dt = parse_datetime_input(message.text or "")
    if parsed_dt is None:
        await message.answer(
            "⚠️ Vaqt formati noto'g'ri kiritildi.\n\n"
            "Iltimos, qaytadan kiriting:\n"
            "Masalan: <code>14:30</code> yoki <code>22.09 18:00</code>"
        )
        return

    catalog = CatalogService(session)
    await catalog.tests.update_fields(test, starts_at=parsed_dt)
    await state.clear()

    await message.answer(
        f"✅ Test ochilish vaqti belgilandi: <b>{fmt_datetime(parsed_dt)}</b>\n\n"
        f"Bosh menyu orqali testga qaytishingiz mumkin: /menu"
    )


@router.message(TestSchedule.end_time, F.text)
async def process_schedule_end(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Yopilish vaqtini saqlash."""
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("✖️ Bekor qilindi.")
        return

    data = await state.get_data()
    test_id = data.get("schedule_test_id")
    if not test_id:
        await state.clear()
        return

    test = await _load_owned(session, test_id, user)
    if test is None:
        await state.clear()
        await message.answer(uz.NO_PERMISSION)
        return

    parsed_dt = parse_datetime_input(message.text or "")
    if parsed_dt is None:
        await message.answer(
            "⚠️ Vaqt formati noto'g'ri kiritildi.\n\n"
            "Iltimos, qaytadan kiriting:\n"
            "Masalan: <code>21:00</code> yoki <code>22.09 21:00</code>"
        )
        return

    catalog = CatalogService(session)
    await catalog.tests.update_fields(test, ends_at=parsed_dt)
    await state.clear()

    await message.answer(
        f"✅ Test yopilish vaqti belgilandi: <b>{fmt_datetime(parsed_dt)}</b>\n\n"
        f"Bosh menyu orqali testga qaytishingiz mumkin: /menu"
    )


@router.callback_query(TestCB.filter(F.action == "set_timer"))
async def set_timer_value(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Taymer daqiqasini bazaga saqlaydi."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    mins = max(0, callback_data.value)
    catalog = CatalogService(session)
    await catalog.tests.update_fields(test, time_limit_sec=mins * 60)

    if mins > 0:
        await safe_answer(callback, f"✅ Taymer: {mins} daqiqa qilib belgilandi", alert=True)
    else:
        await safe_answer(callback, "✅ Taymer olib tashlandi (Cheksiz)", alert=True)

    await open_timer_menu(callback, callback_data, user, session)


@router.callback_query(TestCB.filter(F.action == "delete"))
async def confirm_delete(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """O'chirishdan oldin tasdiqlash so'raladi."""
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    participants = await AttemptRepository(session).count_finished_by_test(test.id)

    warning = (
        f"🗑 <b>Testni o'chirasizmi?</b>\n"
        f"{uz.LINE}\n\n"
        f"📝 <b>{uz.escape(test.title)}</b>\n"
        f"🔑 Kod: <b>{test.number}</b>\n\n"
    )

    if participants:
        warning += (
            f"⚠️ Bu testga <b>{participants} ta</b> javob berilgan.\n"
            f"Ularning natijalari ham o'chib ketadi.\n\n"
        )

    warning += "<i>Bu amalni orqaga qaytarib bo'lmaydi.</i>"

    await safe_edit(callback, warning, reply_markup=confirm_delete_keyboard(test.id))


@router.callback_query(TestCB.filter(F.action == "delete_yes"))
async def do_delete(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    number = test.number

    try:
        await CatalogService(session).delete(test, user)
    except TestLabError as error:
        await safe_answer(callback, error.user_text()[:200], alert=True)
        return

    await safe_answer(callback, "🗑 O'chirildi")
    await _render_my_tests(callback, user, session, 1)
    log.info("Test o'chirildi: №%s (user=%s)", number, user.telegram_id)


@router.callback_query(TestCB.filter(F.action == "images"))
async def show_images(
    callback: CallbackQuery,
    callback_data: TestCB,
    session: AsyncSession,
) -> None:
    """Test rasmlarini qayta yuborish."""
    await safe_answer(callback, uz.SENDING_IMAGES)

    if callback.message is None:
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get(callback_data.test_id)

    if test is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    media = await catalog.list_media(test)

    if not media:
        await callback.message.answer(uz.NO_IMAGES)
        return

    await send_media_group(callback.message, media)


# ======================================================================
#  JAVOB BERGANLAR
# ======================================================================

@router.callback_query(PeopleCB.filter(F.action == "analysis"))
async def show_analysis(
    callback: CallbackQuery,
    callback_data: PeopleCB,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Savolma-savol tahlil: qaysi savol qiyin bo'lgan, qaysi variant
    chalg'itgan, kalitda xato bormi.

    Ilgari bu ma'lumot faqat Excel faylida bor edi.
    """
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    attempts = AttemptRepository(session)
    participants = await attempts.count_finished_by_test(test.id)
    rows = await AssessmentService(session).question_breakdown(test)

    #  Sahifalash `Page` orqali — qolgan ro'yxatlar bilan bir xil
    #  ko'rinsin. Elementlar kerak emas, faqat sanoq.
    page = Page(
        items=[],
        total=len(rows),
        page=max(1, callback_data.page),
        per_page=uz.ANALYSIS_PER_PAGE,
    )

    back = (
        TestCB(action="manage", test_id=test.id).pack()
        if test.author_id == user.id
        else AdminCB(action="tests", page=1).pack()
    )

    await safe_edit(
        callback,
        uz.question_analysis(test, rows, participants, page=page.page),
        reply_markup=analysis_keyboard(test.id, page, back_callback=back),
    )


@router.callback_query(PeopleCB.filter(F.action == "excel"))
async def send_excel(
    callback: CallbackQuery,
    callback_data: PeopleCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Natijalarni `.xlsx` fayl qilib yuboradi."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    if callback.message is None:
        return

    attempts = AttemptRepository(session)
    participants = await attempts.count_finished_by_test(test.id)

    if participants == 0:
        await safe_answer(callback, uz.NOBODY_ANSWERED, alert=True)
        return

    await safe_answer(callback, uz.EXCEL_BUILDING)

    from modules.analytics.excel import TestReportBuilder

    builder = TestReportBuilder(session)

    try:
        data, total = await builder.build(test)
    except Exception as error:
        #  Hisobot yig'ishdagi xato butun botni to'xtatmasligi kerak
        log.exception("Excel yig'ilmadi: %s", error)
        await callback.message.answer(
            "⚠️ Jadval tayyorlashda xatolik. Administratorlarga xabar berildi."
        )
        return

    if len(data) > MAX_DOCUMENT_BYTES:
        await callback.message.answer(
            f"⚠️ Jadval juda katta ({len(data) // 1024 // 1024} MB)."
        )
        return

    await callback.message.answer_document(
        document=BufferedInputFile(data, filename=builder.filename(test)),
        caption=uz.excel_caption(test, total),
    )

    log.info(
        "Excel yuborildi: test=№%s -> user=%s (%d ta, %d bayt)",
        test.number, user.telegram_id, total, len(data),
    )


# ======================================================================
#  TESTNI TAHRIRLASH
# ======================================================================

@router.callback_query(TestCB.filter(F.action == "edit_menu"))
async def open_edit_menu(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    key_display = test.answer_key or "(belgilanmagan)"
    questions_count = len(test.answer_key) if test.answer_key else test.questions_count
    await safe_edit(
        callback,
        f"✏️ <b>TESTNI TAHRIRLASH</b>\n"
        f"{uz.LINE}\n\n"
        f"📝 Nom: <b>{uz.escape(test.title)}</b>\n"
        f"🔑 Kod: <b>{test.number}</b>\n"
        f"🔑 Kalit: <code>{uz.escape(key_display)}</code> ({questions_count} ta savol)\n\n"
        f"Nimani o'zgartirmoqchisiz?",
        reply_markup=test_edit_keyboard(test.id),
    )


@router.callback_query(TestCB.filter(F.action == "edit_title"))
async def ask_edit_title(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await state.set_state(TestEdit.title)
    await state.update_data(test_id=test.id)

    if callback.message:
        await callback.message.answer(
            f"✏️ <b>Yangi test nomini kiriting:</b>\n\n"
            f"Hozirgi nom: <b>{uz.escape(test.title)}</b>\n\n"
            f"<i>Bekor qilish uchun /cancel yuboring.</i>"
        )


@router.message(TestEdit.title, F.text)
async def save_edit_title(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Tahrirlash bekor qilindi.")
        return

    new_title = message.text.strip()
    if not new_title or len(new_title) > 150:
        await message.answer("⚠️ Nom uzunligi 1 dan 150 belgigacha bo'lishi kerak. Qaytadan kiriting:")
        return

    data = await state.get_data()
    test_id = data.get("test_id")

    test = await _load_owned(session, test_id, user)
    if test is None:
        await state.clear()
        await message.answer(uz.NO_PERMISSION)
        return

    catalog = CatalogService(session)
    await catalog.tests.update_fields(test, title=new_title)
    await state.clear()

    await message.answer(
        f"✅ <b>Test nomi o'zgartirildi!</b>\n\n"
        f"Yangi nom: <b>{uz.escape(new_title)}</b>"
    )


@router.callback_query(TestCB.filter(F.action == "edit_key"))
async def ask_edit_key(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    if not test.answer_key:
        await safe_answer(callback, "⚠️ Bu test uchun hali kalit o'rnatilmagan.", alert=True)
        return

    await state.set_state(TestEdit.key)
    await state.update_data(test_id=test.id)

    if callback.message:
        await callback.message.answer(
            f"🔑 <b>TUZATILGAN JAVOBLAR KALITINI YUBORING</b>\n"
            f"{uz.LINE}\n\n"
            f"Hozirgi kalit: <code>{uz.escape(test.answer_key)}</code> ({len(test.answer_key)} ta savol)\n\n"
            f"⚠️ <b>MUHIM:</b> Savollar soni (<b>{len(test.answer_key)} ta</b>) aynan bir xil bo'lishi kerak.\n"
            f"Kalit yangilangach, barcha o'quvchilarning ballari va o'rinlari <b>avtomatik qayta hisoblanadi</b>!\n\n"
            f"<i>Bekor qilish uchun /cancel yuboring.</i>"
        )


@router.message(TestEdit.key, F.text)
async def save_edit_key(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Bekor qilindi.")
        return

    data = await state.get_data()
    test_id = data.get("test_id")

    test = await _load_owned(session, test_id, user)
    if test is None:
        await state.clear()
        await message.answer(uz.NO_PERMISSION)
        return

    catalog = CatalogService(session)

    try:
        old_key, new_key = await catalog.correct_answer_key(test, user, message.text)
    except TestLabError as error:
        count_info = f" ({len(test.answer_key)} ta savol)" if test.answer_key else ""
        await message.answer(
            f"⚠️ <b>Xatolik:</b> {error.user_text()}\n\n"
            f"Iltimos, qaytadan to'g'ri kalitni yuboring{count_info} yoki /cancel yuboring."
        )
        return

    recalculated = await AssessmentService(session).recalculate_all(test)
    await state.clear()

    await message.answer(
        f"✅ <b>Javoblar kaliti tuzatildi!</b>\n"
        f"{uz.LINE}\n\n"
        f"Eski kalit: <code>{old_key}</code>\n"
        f"Yangi kalit: <code>{new_key}</code>\n\n"
        f"🔄 <b>{len(recalculated)} ta</b> o'quvchining natijalari avtomatik qayta hisoblandi!"
    )


@router.callback_query(TestCB.filter(F.action == "edit_media"))
async def ask_edit_media(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await state.set_state(TestEdit.media)
    await state.update_data(test_id=test.id)

    catalog = CatalogService(session)
    count = await catalog.media_count(test)

    if callback.message:
        await callback.message.answer(
            f"🖼 <b>TESTGA FAYL YOKI RASM QO'SHISH</b>\n"
            f"{uz.LINE}\n\n"
            f"Hozirgi rasmlar: <b>{count} ta</b>\n\n"
            f"Test uchun rasm yoki fayl yuboring. Jarayonni yakunlash uchun /cancel yuboring."
        )


@router.message(TestEdit.media, F.photo | F.document | F.text)
async def save_edit_media(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("✅ Rasmlar qo'shish yakunlandi.")
        return

    data = await state.get_data()
    test_id = data.get("test_id")

    test = await _load_owned(session, test_id, user)
    if test is None:
        await state.clear()
        await message.answer(uz.NO_PERMISSION)
        return

    file_id = None
    file_unique_id = None
    media_type = "photo"

    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        media_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_unique_id = message.document.file_unique_id
        media_type = "document"
    else:
        await message.answer("⚠️ Iltimos, rasm yoki fayl yuboring, yoki tugatish uchun /cancel bosing.")
        return

    catalog = CatalogService(session)
    try:
        await catalog.add_media(
            test,
            user,
            file_id=file_id,
            file_unique_id=file_unique_id,
            media_type=media_type,
        )
    except TestLabError as error:
        await message.answer(f"⚠️ {error.user_text()}")
        return

    count = await catalog.media_count(test)
    await message.answer(
        f"✅ <b>Fayl qo'shildi!</b> (Jami: {count} ta)\n"
        f"Yana rasm/fayl yuborishingiz yoki /cancel bosishingiz mumkin."
    )


# ======================================================================
#  KANALGA ULASHISH VA NATIJALARNI E'LON QILISH
# ======================================================================

@router.callback_query(TestCB.filter(F.action == "share_channel"))
async def start_channel_share(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Kanal yoki guruhga test ulashish: tayyor reklama posti va 1-klikda ulashish."""
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    bot_user = settings.bot.username
    start_link = f"https://t.me/{bot_user}?start=t{test.number}"

    timer_str = f"{test.time_limit_sec // 60} daqiqa" if test.time_limit_sec > 0 else "Cheksiz"
    q_count = len(test.answer_key) if test.answer_key else test.questions_count
    cat_title = test.category.label if test.category else "Umumiy"

    promo_text = (
        f"📢 <b>YANGI TEST E'LON QILINDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 <b>Test:</b> {uz.escape(test.title)}\n"
        f"📚 <b>Fan:</b> {cat_title}\n"
        f"❓ <b>Savollar soni:</b> {q_count} ta\n"
        f"⏱ <b>Ajratilgan vaqt:</b> {timer_str}\n"
        f"🔑 <b>Test kodi:</b> <code>{test.number}</code>\n\n"
        f"🚀 Testni boshlash uchun pastdagi tugmani bosing yoki botga <code>{test.number}</code> kodini yuboring!"
    )

    # Telegram share havolasi
    share_msg = f"📢 Yangi test: {test.title}\n🔑 Kod: {test.number}\n👉 Testni yechish: {start_link}"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(start_link)}&text={urllib.parse.quote(share_msg)}"

    share_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↗️ Guruh yoki Kanalga ulashish",
                    url=share_url,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Bot orqali avtomatik kanalga joylash",
                    callback_data=TestCB(action="ask_bot_channel", test_id=test.id).pack(),
                )
            ],
            [
                back_button(TestCB(action="manage", test_id=test.id).pack()),
                home_button(),
            ],
        ]
    )

    if callback.message:
        await callback.message.answer(
            f"📋 <b>Guruh va kanallar uchun tayyor reklama xabari:</b>\n\n"
            f"{promo_text}\n\n"
            f"<i>💡 <b>«↗️ Guruh yoki Kanalga ulashish»</b> tugmasini bossangiz, Telegram orqali xohlagan guruhingizga 1 ta bosish bilan ulashishingiz mumkin (bot admin bo'lishi shart emas)!</i>",
            reply_markup=share_kb,
        )


@router.callback_query(TestCB.filter(F.action == "ask_bot_channel"))
async def ask_bot_channel(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Bot admin bo'lgan kanalga avtomatik joylash so'rovi."""
    await safe_answer(callback)

    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await state.set_state(ChannelShare.target)
    await state.update_data(share_test_id=test.id)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=uz.BTN_CANCEL,
                    callback_data=TestCB(action="manage", test_id=test.id).pack(),
                )
            ]
        ]
    )

    if callback.message:
        await callback.message.answer(uz.ASK_CHANNEL_TARGET, reply_markup=cancel_kb)


@router.message(ChannelShare.target)
async def process_channel_target(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Kanal yoki guruhni qabul qilish, tekshirish va testni joylash."""
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("✖️ Bekor qilindi.")
        return

    data = await state.get_data()
    test_id = data.get("share_test_id")
    if not test_id:
        await state.clear()
        return

    test = await _load_owned(session, test_id, user)
    if test is None:
        await state.clear()
        await message.answer(uz.NO_PERMISSION)
        return

    chat_id = None
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
    elif message.text:
        text = message.text.strip()
        if text.startswith("https://t.me/"):
            text = "@" + text.removeprefix("https://t.me/").strip("/")
        if text.startswith("-100") or (text.startswith("-") and text[1:].isdigit()):
            chat_id = int(text)
        elif text.startswith("@"):
            chat_id = text
        elif " " not in text and not text.startswith("/"):
            chat_id = f"@{text}"

    if not chat_id:
        await message.answer(
            "⚠️ Kanal topilmadi. Iltimos, kanal username'ini (@kanal) yozing "
            "yoki kanaldan xabarni bu yerga Forward qiling."
        )
        return

    bot = message.bot
    if bot is None:
        await state.clear()
        return

    try:
        me = await bot.get_me()
        chat_member = await bot.get_chat_member(chat_id=chat_id, user_id=me.id)
    except Exception as err:
        log.warning("Kanal a'zoligini tekshirishda xatolik (%s): %s", chat_id, err)
        await message.answer(uz.CHANNEL_NOT_ADMIN)
        return

    if chat_member.status not in ("administrator", "creator"):
        await message.answer(uz.CHANNEL_NOT_ADMIN)
        return

    post_text = uz.channel_test_post(test, me.username or "")
    post_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Testni yechish (Boshlash)",
                    url=f"https://t.me/{me.username}?start=t{test.number}",
                )
            ]
        ]
    )

    catalog = CatalogService(session)
    media_list = await catalog.media.list_by_test(test.id)

    sent_msg = None
    if media_list and media_list[0].media_type == "photo":
        try:
            sent_msg = await bot.send_photo(
                chat_id=chat_id,
                photo=media_list[0].file_id,
                caption=post_text,
                reply_markup=post_kb,
            )
        except Exception as err:
            log.warning("Kanalga rasm bilan post chiqarilmadi (%s): %s", chat_id, err)

    if sent_msg is None:
        try:
            sent_msg = await bot.send_message(
                chat_id=chat_id,
                text=post_text,
                reply_markup=post_kb,
            )
        except Exception as err:
            log.exception("Kanalga xabar yuborishda xatolik (%s): %s", chat_id, err)
            await message.answer(uz.CHANNEL_NOT_ADMIN)
            return

    actual_chat_id = sent_msg.chat.id
    actual_msg_id = sent_msg.message_id

    await catalog.tests.update_fields(
        test,
        channel_id=actual_chat_id,
        channel_message_id=actual_msg_id,
    )
    await state.clear()

    await message.answer(
        uz.CHANNEL_POST_SUCCESS,
        reply_markup=test_manage_keyboard(test),
    )


@router.callback_query(TestCB.filter(F.action == "post_results"))
async def publish_results_to_channel(
    callback: CallbackQuery,
    callback_data: TestCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Natijalar reytingini kanalga e'lon qilish."""
    test = await _load_owned(session, callback_data.test_id, user)
    if test is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    if not test.channel_id:
        await safe_answer(callback, "⚠️ Avval testni kanalga ulashing!", alert=True)
        return

    attempt_repo = AttemptRepository(session)
    page = await attempt_repo.list_by_test(test.id, page=1, per_page=10, by_rank=True)
    total_count = await attempt_repo.count_finished_by_test(test.id)

    if total_count == 0:
        await safe_answer(callback, uz.NO_PARTICIPANTS_YET, alert=True)
        return

    leaderboard_text = uz.channel_leaderboard(test, page.items, total_count)
    bot = callback.bot
    if bot is None:
        return

    try:
        try:
            await bot.send_message(
                chat_id=test.channel_id,
                text=leaderboard_text,
                reply_to_message_id=test.channel_message_id if test.channel_message_id else None,
            )
        except Exception:
            await bot.send_message(
                chat_id=test.channel_id,
                text=leaderboard_text,
            )

        test.results_posted_at = utcnow()
        await session.commit()
        await safe_answer(callback, "✅ Natijalar kanalga e'lon qilindi!", alert=True)
    except Exception as err:
        log.exception("Natijalarni kanalga yuborishda xato: %s", err)
        await safe_answer(
            callback,
            "❌ Kanalga natijalarni yuborishda xatolik yuz berdi. Bot kanalda admin ekanligini tekshiring.",
            alert=True,
        )

    await manage_test(callback, callback_data, user, session)


