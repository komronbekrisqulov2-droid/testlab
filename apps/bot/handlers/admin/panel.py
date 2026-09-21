"""
Admin paneli.

Asosiy talab: admin uchta narsani BIR NECHA TUGMADA olishi kerak —
foydalanuvchilar, test yechganlar, reytinglar. Har biri botda ro'yxat
va Excel ko'rinishida.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import IsAdmin
from apps.bot.keyboards.admin import (
    board_keyboard,
    cancel_search_keyboard,
    panel_keyboard,
    period_label,
    solvers_keyboard,
    tests_keyboard,
    user_card_keyboard,
    users_keyboard,
)
from apps.bot.keyboards.callbacks import AdminCB
from apps.bot.states import AdminSearch
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.datetime_utils import days_ago
from core.logging import get_logger
from core.security.permissions import Permission, Role
from modules.analytics.excel import AdminReportBuilder
from modules.assessment.repository import AttemptRepository
from modules.catalog.repository import TestRepository
from modules.identity.models import User
from modules.identity.repository import UserRepository

log = get_logger(__name__)

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PER_PAGE = 10
BOARD_SIZE = 15

#  Excel'ga chiqariladigan maksimal qatorlar — juda katta hisobot
#  ham botni ham Telegram'ni qiynaydi
MAX_EXPORT_ROWS = 5000


def _since(period: int):
    """Davr filtri: 0 = butun davr."""
    return days_ago(period) if period > 0 else None


# ======================================================================
#  DASHBOARD
# ======================================================================

async def _render_panel(callback: CallbackQuery, session: AsyncSession) -> None:
    users = await UserRepository(session).stats()
    tests = await TestRepository(session).stats()
    attempts = await AttemptRepository(session).global_stats()

    await safe_edit(
        callback,
        uz.admin_dashboard(users, tests, attempts),
        reply_markup=panel_keyboard(),
    )


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.clear()

    users = await UserRepository(session).stats()
    tests = await TestRepository(session).stats()
    attempts = await AttemptRepository(session).global_stats()

    await message.answer(
        uz.admin_dashboard(users, tests, attempts),
        reply_markup=panel_keyboard(),
    )


@router.callback_query(AdminCB.filter(F.action == "panel"))
async def open_panel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)
    await state.clear()
    await _render_panel(callback, session)


# ======================================================================
#  👥 FOYDALANUVCHILAR
# ======================================================================

@router.callback_query(AdminCB.filter(F.action == "users"))
async def show_users(
    callback: CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)

    page = await UserRepository(session).list_all(
        page=max(1, callback_data.page), per_page=PER_PAGE
    )

    await safe_edit(
        callback,
        uz.admin_users_page(page, "FOYDALANUVCHILAR"),
        reply_markup=users_keyboard(page),
    )


@router.callback_query(AdminCB.filter(F.action == "user"))
async def show_user_card(
    callback: CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
    user: User,
) -> None:
    """Bitta foydalanuvchi kartochkasi."""
    await safe_answer(callback)

    target = await UserRepository(session).get(callback_data.target_id)
    if target is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    stats = await AttemptRepository(session).user_stats(target.id)

    await safe_edit(
        callback,
        uz.admin_user_card(target, stats),
        reply_markup=user_card_keyboard(
            target, callback_data.page, is_super=user.role == Role.SUPER_ADMIN.value
        ),
    )


@router.callback_query(AdminCB.filter(F.action.in_({"ban", "unban"})))
async def toggle_ban(
    callback: CallbackQuery,
    callback_data: AdminCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Bloklash / blokdan chiqarish."""
    users = UserRepository(session)
    target = await users.get(callback_data.target_id)

    if target is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    #  O'zini yoki o'zidan yuqori rolni bloklab bo'lmaydi.
    #  Busiz admin o'zini bloklab, botni boshqarishdan mahrum bo'lardi.
    if target.id == user.id:
        await safe_answer(callback, "⚠️ O'zingizni bloklay olmaysiz", alert=True)
        return

    if target.role == Role.SUPER_ADMIN.value and user.role != Role.SUPER_ADMIN.value:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    if callback_data.action == "ban":
        await users.ban(target, reason="Administrator qarori")
        await safe_answer(callback, "🚫 Bloklandi")
        log.info("Ban: %s -> %s", user.telegram_id, target.telegram_id)
    else:
        await users.unban(target)
        await safe_answer(callback, "✅ Blokdan chiqarildi")
        log.info("Unban: %s -> %s", user.telegram_id, target.telegram_id)

    await show_user_card(callback, callback_data, session, user)


@router.callback_query(AdminCB.filter(F.action == "role"))
async def change_role(
    callback: CallbackQuery,
    callback_data: AdminCB,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Rolni almashtirish: o'quvchi ↔ o'qituvchi.

    `period` maydoni bu yerda yangi rolni bildiradi (1 = o'qituvchi).
    Callback'da bo'sh maydon bor edi, yangi CallbackData yasashdan
    ko'ra shuni ishlatgan ma'qul — 64 bayt chegarasi bor.
    """
    users = UserRepository(session)
    target = await users.get(callback_data.target_id)

    if target is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    if not user.can(Permission.USERS_SET_ROLE):
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    #  Adminning rolini o'zgartirib bo'lmaydi (faqat super admin)
    if target.is_admin and user.role != Role.SUPER_ADMIN.value:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    if callback_data.period == 1:
        new_role = Role.TEACHER.value
    elif callback_data.period == 2:
        if user.role != Role.SUPER_ADMIN.value:
            await safe_answer(
                callback,
                "⚠️ Faqat Bosh Administrator (Super Admin) admin tayinlay oladi.",
                alert=True,
            )
            return
        new_role = Role.ADMIN.value
    else:
        new_role = Role.STUDENT.value

    was_teacher = target.is_teacher

    await users.set_role(target, new_role)

    await safe_answer(callback, f"✅ {target.role_title}")
    log.info("Rol: %s -> %s = %s", user.telegram_id, target.telegram_id, new_role)

    #  Yangi o'qituvchiga tabrik va qo'llanma yuboramiz — u so'rov
    #  yuborgan bo'lishi mumkin va javobni kutayotgandir
    if new_role == Role.TEACHER.value and not was_teacher:
        try:
            await callback.bot.send_message(target.telegram_id, uz.TEACHER_GRANTED)
        except Exception as error:
            #  Foydalanuvchi botni bloklagan bo'lishi mumkin — normal holat
            log.debug("Tabrik yetkazilmadi (%s): %s", target.telegram_id, error)

    await show_user_card(callback, callback_data, session, user)


# ------------------------------------------------------------------
#  Qidiruv
# ------------------------------------------------------------------

@router.callback_query(AdminCB.filter(F.action == "search"))
async def ask_search(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(callback)
    await state.set_state(AdminSearch.query)
    await safe_edit(callback, uz.ADMIN_ASK_SEARCH, reply_markup=cancel_search_keyboard())


@router.message(AdminSearch.query, F.text)
async def do_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    query = (message.text or "").strip()

    if len(query) < 2:
        await message.answer("⚠️ Kamida 2 ta belgi kiriting.")
        return

    await state.clear()

    page = await UserRepository(session).search(query, page=1, per_page=PER_PAGE)

    await message.answer(
        uz.admin_users_page(page, f"QIDIRUV: {uz.escape(query)}"),
        reply_markup=users_keyboard(page),
    )


# ======================================================================
#  ✍️ TEST YECHGANLAR
# ======================================================================

@router.callback_query(AdminCB.filter(F.action == "solvers"))
async def show_solvers(
    callback: CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
) -> None:
    """Kim qaysi testni yechgani — davr filtri bilan."""
    await safe_answer(callback)

    period = callback_data.period
    page = await AttemptRepository(session).list_recent(
        page=max(1, callback_data.page),
        per_page=PER_PAGE,
        since=_since(period),
    )

    await safe_edit(
        callback,
        uz.admin_solvers_page(page, period_label(period)),
        reply_markup=solvers_keyboard(page, period),
    )


# ======================================================================
#  🏆 REYTINGLAR
# ======================================================================

@router.callback_query(AdminCB.filter(F.action == "board"))
async def show_board(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await safe_answer(callback)

    users = UserRepository(session)
    top = await users.top_by_xp(BOARD_SIZE)
    rank = await users.xp_rank(user)

    await safe_edit(
        callback,
        uz.leaderboard(top, user, rank),
        reply_markup=board_keyboard(),
    )


# ======================================================================
#  📝 TESTLAR
# ======================================================================

@router.callback_query(AdminCB.filter(F.action == "tests"))
async def show_tests(
    callback: CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
) -> None:
    """
    Barcha testlar.

    Testni bosganda uni yechganlar ro'yxati ochiladi — bu admin uchun
    eng ko'p kerak bo'ladigan ma'lumot.
    """
    await safe_answer(callback)

    page = await TestRepository(session).list_all(
        page=max(1, callback_data.page), per_page=PER_PAGE
    )

    lines = ["📝 <b>TESTLAR</b>", uz.LINE, "", f"Jami: <b>{page.total} ta</b>", ""]

    if page.is_empty:
        lines.append("<i>Hali test yaratilmagan.</i>")
    else:
        for test in page.items:
            lines.append(
                f"<b>№{test.number}</b> · {uz.escape(test.title)}\n"
                f"     {test.status_label} · {test.questions_count} savol · "
                f"👥 {test.attempts_count} · 📈 {test.avg_score:g}%"
            )
        lines += ["", "<i>Natijalarni ko'rish uchun testni bosing.</i>"]

    await safe_edit(callback, "\n".join(lines), reply_markup=tests_keyboard(page))


# ======================================================================
#  📊 EXCEL EKSPORT
# ======================================================================

async def _send_excel(
    callback: CallbackQuery,
    data: bytes,
    filename: str,
    caption: str,
) -> None:
    """Tayyor faylni yuboradi."""
    if callback.message is None:
        return

    await callback.message.answer_document(
        document=BufferedInputFile(data, filename=filename),
        caption=caption,
    )


@router.callback_query(AdminCB.filter(F.action == "excel_users"))
async def export_users(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Barcha foydalanuvchilarni Excel'ga chiqaradi."""
    await safe_answer(callback, uz.EXCEL_BUILDING)

    users_repo = UserRepository(session)
    rows = await users_repo.list_for_export()

    if not rows:
        await safe_answer(callback, "Foydalanuvchi yo'q", alert=True)
        return

    truncated = len(rows) > MAX_EXPORT_ROWS
    rows = rows[:MAX_EXPORT_ROWS]

    builder = AdminReportBuilder(session)

    try:
        data, total = await builder.build_users(rows)
    except Exception as error:
        log.exception("Foydalanuvchilar hisoboti yig'ilmadi: %s", error)
        if callback.message:
            await callback.message.answer("⚠️ Jadval tayyorlashda xatolik.")
        return

    caption = f"👥 <b>Foydalanuvchilar</b>\n\nJami: <b>{total} ta</b>"
    if truncated:
        caption += f"\n\n⚠️ Birinchi {MAX_EXPORT_ROWS} ta ko'rsatildi."

    await _send_excel(callback, data, builder.users_filename(), caption)
    log.info("Excel (foydalanuvchilar): %d ta -> %s", total, user.telegram_id)


@router.callback_query(AdminCB.filter(F.action == "excel_solvers"))
async def export_solvers(
    callback: CallbackQuery,
    callback_data: AdminCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Test yechganlarni Excel'ga chiqaradi."""
    await safe_answer(callback, uz.EXCEL_BUILDING)

    period = callback_data.period
    label = period_label(period)

    attempts = await AttemptRepository(session).list_recent_for_export(
        since=_since(period)
    )

    if not attempts:
        await safe_answer(callback, "Bu davrda javob yo'q", alert=True)
        return

    truncated = len(attempts) > MAX_EXPORT_ROWS
    attempts = attempts[:MAX_EXPORT_ROWS]

    builder = AdminReportBuilder(session)

    try:
        data, total = await builder.build_solvers(attempts, period_label=label)
    except Exception as error:
        log.exception("Yechganlar hisoboti yig'ilmadi: %s", error)
        if callback.message:
            await callback.message.answer("⚠️ Jadval tayyorlashda xatolik.")
        return

    unique = len({attempt.user_id for attempt in attempts})
    caption = (
        f"✍️ <b>Test yechganlar</b>\n\n"
        f"📅 Davr: <b>{label}</b>\n"
        f"📊 Topshiriqlar: <b>{total} ta</b>\n"
        f"👥 Noyob o'quvchilar: <b>{unique} ta</b>"
    )
    if truncated:
        caption += f"\n\n⚠️ Birinchi {MAX_EXPORT_ROWS} ta ko'rsatildi."

    await _send_excel(callback, data, builder.solvers_filename(label), caption)
    log.info("Excel (yechganlar): %d ta -> %s", total, user.telegram_id)
