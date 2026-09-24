"""
Sinf va guruhlar (Classroom) boshqaruvi — o'qituvchi interfeysi.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import HasPermission, IsRegistered
from apps.bot.keyboards.callbacks import ClassCB, MenuCB
from apps.bot.keyboards.inline import (
    back_button,
    classroom_detail_keyboard,
    classroom_ranking_keyboard,
    classroom_students_keyboard,
    classrooms_list_keyboard,
    home_button,
    student_classroom_detail_keyboard,
    student_classrooms_list_keyboard,
)
from apps.bot.states import ClassroomCreate
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.config import settings
from core.logging import get_logger
from core.security.permissions import Permission
from modules.catalog.service import CatalogService
from modules.classroom.models import Classroom
from modules.classroom.repository import ClassroomRepository
from modules.identity.models import User

log = get_logger(__name__)

router = Router(name="teacher_classroom")
router.message.filter(IsRegistered())


async def _load_owned_classroom(
    session: AsyncSession,
    class_id: int,
    user: User,
) -> Classroom | None:
    """Guruhni yuklaydi va egaligini tekshiradi."""
    cls_repo = ClassroomRepository(session)
    classroom = await cls_repo.get(class_id)
    if classroom is None:
        return None
    if classroom.teacher_id != user.id and not user.is_admin:
        return None
    return classroom


# ======================================================================
#  GURUHLAR RO'YXATI (O'QITUVCHI VA O'QUVCHI)
# ======================================================================

@router.message(Command("classes"))
@router.callback_query(ClassCB.filter(F.action == "list"))
async def open_classrooms_list(
    event: Message | CallbackQuery,
    user: User,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    """Guruhlar ro'yxati (o'qituvchi yoki o'quvchi)."""
    if state:
        await state.clear()

    if not user.is_teacher:
        return await open_student_classrooms_list(event, user, session, state)

    if isinstance(event, CallbackQuery):
        await safe_answer(event)

    cls_repo = ClassroomRepository(session)
    classrooms = await cls_repo.list_by_teacher(user.id)

    text = (
        f"👥 <b>MENING GURUHLARIM (SINFLAR)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Jami guruhlar soni: <b>{len(classrooms)} ta</b>\n\n"
        f"<i>Guruh orqali o'quvchilaringizni sinflarga ajratishingiz, "
        f"maxsus taklif havolasi orqali a'zo qilishingiz, yopiq testlar "
        f"o'tkazishingiz va umumiy sinf reytingini kuzatishingiz mumkin.</i>\n\n"
        f"Boshqarish uchun guruhni tanlang yoki yangisini oching:"
    )

    if isinstance(event, CallbackQuery):
        await safe_edit(event, text, reply_markup=classrooms_list_keyboard(classrooms))
    else:
        await event.answer(text, reply_markup=classrooms_list_keyboard(classrooms))


@router.callback_query(ClassCB.filter(F.action == "student_list"))
async def open_student_classrooms_list(
    event: Message | CallbackQuery,
    user: User,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    """O'quvchi a'zo bo'lgan guruhlar."""
    if state:
        await state.clear()
    if isinstance(event, CallbackQuery):
        await safe_answer(event)

    cls_repo = ClassroomRepository(session)
    classrooms = await cls_repo.list_by_student(user.id)

    lines = [
        "👥 <b>MENING GURUHLARIM (SINFLARIM)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if not classrooms:
        lines.append("<i>Siz hali birorta ham guruhga a'zo emassiz.</i>\n\n"
                     "💡 <i>O'qituvchingiz yuborgan maxsus taklif havolasini (link) bossangiz, "
                     "avtomatik ravishda uning sinfiga qo'shilasiz va yopiq testlarni yecha olasiz.</i>")
    else:
        lines.append(f"Siz <b>{len(classrooms)} ta</b> guruhga a'zosiz.\n"
                     f"Guruhdagi o'rningiz va reytingni ko'rish uchun tanlang:")

    kb = student_classrooms_list_keyboard(classrooms)
    if isinstance(event, CallbackQuery):
        await safe_edit(event, "\n".join(lines), reply_markup=kb)
    else:
        await event.answer("\n".join(lines), reply_markup=kb)


@router.callback_query(ClassCB.filter(F.action == "student_view"))
async def view_student_classroom(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """O'quvchi uchun bitta guruh tafsilotlari ekrani."""
    await safe_answer(callback)
    cls_repo = ClassroomRepository(session)
    classroom = await cls_repo.get(callback_data.class_id)
    if classroom is None:
        await safe_answer(callback, "Guruh topilmadi.", alert=True)
        return

    # A'zolik tekshiruvi
    if not await cls_repo.is_member(classroom.id, user.id):
        await safe_answer(callback, "Siz bu guruhga a'zo emassiz.", alert=True)
        return

    teacher_name = classroom.teacher.full_name if classroom.teacher else "—"
    members_count = await cls_repo.count_members(classroom.id)

    text = (
        f"🏫 <b>GURUH: «{uz.escape(classroom.name)}»</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>O'qituvchi:</b> {uz.escape(teacher_name)}\n"
        f"👥 <b>Sinfdoshlar soni:</b> {members_count} nafar\n\n"
        f"<i>Ushbu guruhdagi barcha o'quvchilar reytingini ko'rish uchun "
        f"«Sinf reytingi» tugmasini bosing.</i>"
    )
    kb = student_classroom_detail_keyboard(classroom.id)
    await safe_edit(callback, text, reply_markup=kb)


@router.callback_query(ClassCB.filter(F.action == "student_leave"))
async def leave_student_classroom(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """O'quvchi guruhdan chiqishi."""
    cls_repo = ClassroomRepository(session)
    classroom = await cls_repo.get(callback_data.class_id)
    if classroom is None:
        await safe_answer(callback, "Guruh topilmadi.", alert=True)
        return

    await cls_repo.remove_member(classroom.id, user.id)
    await session.commit()
    await safe_answer(callback, f"Siz «{classroom.name}» guruhidan chiqdingiz.", alert=True)
    await open_student_classrooms_list(callback, user, session)


# ======================================================================
#  YANGI GURUH YARATISH
# ======================================================================

@router.callback_query(ClassCB.filter(F.action == "create"))
async def prompt_create_classroom(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    """Yangi guruh nomini so'rash."""
    if not user.is_teacher:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await safe_answer(callback)
    await state.set_state(ClassroomCreate.name)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=uz.BTN_CANCEL,
                    callback_data=ClassCB(action="list").pack(),
                )
            ]
        ]
    )
    await safe_edit(
        callback,
        "👥 <b>YANGI GURUH (SINF) YARATISH</b>\n\n"
        "Guruh nomini yozib yuboring:\n"
        "<i>(Masalan: <b>10-A sinf</b> yoki <b>Matematika repetitor</b>)</i>",
        reply_markup=cancel_kb,
    )


@router.message(StateFilter(ClassroomCreate.name))
async def save_new_classroom(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Yangi guruhni saqlash."""
    if not user.is_teacher:
        await state.clear()
        await message.answer(uz.NO_PERMISSION)
        return

    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 80:
        await message.answer("⚠️ Guruh nomi 2 dan 80 tagacha belgidan iborat bo'lishi kerak.")
        return

    await state.clear()
    cls_repo = ClassroomRepository(session)
    classroom = await cls_repo.create(teacher_id=user.id, name=name)
    await session.commit()

    bot_username = settings.bot.username
    join_link = f"https://t.me/{bot_username}?start=cls_{classroom.code}"

    text = (
        f"🎉 <b>«{uz.escape(classroom.name)}» guruhi muvaffaqiyatli yaratildi!</b>\n\n"
        f"🔑 Guruh kodi: <code>{classroom.code}</code>\n"
        f"🔗 <b>Taklif havolasi:</b>\n"
        f"<code>{join_link}</code>\n\n"
        f"<i>Ushbu havolani o'quvchilaringizga yoki sinf guruhiga yuboring. "
        f"Havolani bosgan o'quvchilar avtomatik tarzda guruhingizga qo'shiladi.</i>"
    )
    await message.answer(
        text,
        reply_markup=classroom_detail_keyboard(classroom),
    )


# ======================================================================
#  GURUHNI KO'RISH
# ======================================================================

@router.callback_query(ClassCB.filter(F.action == "view"))
async def view_classroom(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Bitta guruh tafsilotlari."""
    await safe_answer(callback)
    classroom = await _load_owned_classroom(session, callback_data.class_id, user)
    if classroom is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    cls_repo = ClassroomRepository(session)
    members_count = await cls_repo.count_members(classroom.id)

    bot_username = settings.bot.username
    join_link = f"https://t.me/{bot_username}?start=cls_{classroom.code}"

    text = (
        f"👥 <b>Guruh: {uz.escape(classroom.name)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 O'qituvchi: <b>{user.full_name}</b>\n"
        f"🎓 O'quvchilar soni: <b>{members_count} nafar</b>\n"
        f"📝 Biriktirilgan testlar: <b>{classroom.tests_count} ta</b>\n"
        f"🔑 Guruh kodi: <code>{classroom.code}</code>\n\n"
        f"🔗 <b>O'quvchilar uchun taklif havolasi:</b>\n"
        f"<code>{join_link}</code>\n\n"
        f"<i>O'quvchilaringiz shu havolaga kirishlari bilan darhol ushbu guruhga a'zo bo'ladilar.</i>"
    )
    await safe_edit(
        callback,
        text,
        reply_markup=classroom_detail_keyboard(classroom),
    )


# ======================================================================
#  SINF REYTINGI
# ======================================================================

@router.callback_query(ClassCB.filter(F.action == "ranking"))
async def view_classroom_ranking(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Sinf o'quvchilari reytingi (leaderboard)."""
    await safe_answer(callback)
    cls_repo = ClassroomRepository(session)
    classroom = await cls_repo.get(callback_data.class_id)
    if classroom is None:
        await safe_answer(callback, "Guruh topilmadi.", alert=True)
        return

    is_teacher_owner = (classroom.teacher_id == user.id or user.is_admin)
    is_student_member = await cls_repo.is_member(classroom.id, user.id)

    if not is_teacher_owner and not is_student_member:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    leaderboard = await cls_repo.get_leaderboard(classroom.id)

    lines = [
        f"📊 <b>«{uz.escape(classroom.name)}» — SINF REYTINGI</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not leaderboard:
        lines.append("<i>Bu guruhda hali o'quvchilar yo'q yoki ular hali test yechishmagan.</i>")
    else:
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(leaderboard, 1):
            icon = medals[idx - 1] if idx <= 3 else f"<b>{idx}.</b>"
            u_name = row["user"].full_name if row["user"] else "Noma'lum"
            lines.append(
                f"{icon} <b>{uz.escape(u_name)}</b>\n"
                f"   📈 O'rtacha: <b>{row['avg_percentage']}%</b> | "
                f"Yechilgan: <b>{row['tests_count']} ta</b> | "
                f"Eng yaxshi: <b>{row['best_percentage']}%</b>\n"
            )

    await safe_edit(
        callback,
        "\n".join(lines),
        reply_markup=classroom_ranking_keyboard(classroom.id, is_teacher=is_teacher_owner),
    )


# ======================================================================
#  O'QUVCHILAR RO'YXATI VA BOSHQARUV
# ======================================================================

@router.callback_query(ClassCB.filter(F.action == "students"))
async def view_classroom_students(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Guruh a'zolari ro'yxati."""
    await safe_answer(callback)
    classroom = await _load_owned_classroom(session, callback_data.class_id, user)
    if classroom is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    cls_repo = ClassroomRepository(session)
    members = await cls_repo.get_members(classroom.id)

    text = (
        f"👥 <b>«{uz.escape(classroom.name)}» O'QUVCHILARI ({len(members)} nafar)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Guruhdan chiqarish kerak bo'lgan o'quvchi yonidagi «❌ Chiqarish» tugmasini bosing:"
    )

    if not members:
        text += "\n\n<i>Guruhda hali o'quvchilar yo'q. Taklif havolasini yuboring.</i>"

    await safe_edit(
        callback,
        text,
        reply_markup=classroom_students_keyboard(classroom.id, members),
    )


@router.callback_query(ClassCB.filter(F.action == "remove_user"))
async def remove_student_from_class(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """O'quvchini guruhdan chiqarish."""
    classroom = await _load_owned_classroom(session, callback_data.class_id, user)
    if classroom is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    cls_repo = ClassroomRepository(session)
    removed = await cls_repo.remove_member(classroom.id, callback_data.target_id)
    await session.commit()

    if removed:
        await safe_answer(callback, "✅ O'quvchi guruhdan chiqarildi.", alert=True)
    else:
        await safe_answer(callback, "⚠️ O'quvchi topilmadi.")

    await view_classroom_students(callback, callback_data, user, session)


# ======================================================================
#  GURUH TESTLARI
# ======================================================================

@router.callback_query(ClassCB.filter(F.action == "tests"))
async def view_classroom_tests(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Shu guruhga biriktirilgan yopiq testlar."""
    await safe_answer(callback)
    classroom = await _load_owned_classroom(session, callback_data.class_id, user)
    if classroom is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    catalog = CatalogService(session)
    # Guruhga tegishli testlar
    tests = classroom.tests or []

    lines = [
        f"📝 <b>«{uz.escape(classroom.name)}» — GURUH TESTLARI</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "<i>Bu testlar faqat ushbu guruh o'quvchilari uchun ochiq.</i>",
        "",
    ]

    if not tests:
        lines.append("<i>Ushbu guruhga hali birorta test biriktirilmagan.</i>\n\n"
                     "💡 <i>Testlaringiz sozlamasidagi «👥 Guruhga biriktirish» tugmasi "
                     "orqali istalgan testni shu guruhga bog'lashingiz mumkin.</i>")
    else:
        for t in tests:
            status_icon = "🟢" if t.is_published else "🔴"
            rand_icon = "🎲 " if t.is_randomized else ""
            lines.append(f"{status_icon} {rand_icon}<b>№{t.number}</b> · {uz.escape(t.title)}")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [back_button(ClassCB(action="view", class_id=classroom.id).pack())],
            [home_button()],
        ]
    )
    await safe_edit(callback, "\n".join(lines), reply_markup=kb)


# ======================================================================
#  GURUHNI O'CHIRISH
# ======================================================================

@router.callback_query(ClassCB.filter(F.action == "del_conf"))
async def confirm_delete_classroom(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """O'chirishni tasdiqlash ekrani."""
    await safe_answer(callback)
    classroom = await _load_owned_classroom(session, callback_data.class_id, user)
    if classroom is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Ha, o'chirilsin",
                    callback_data=ClassCB(action="delete", class_id=classroom.id).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Bekor qilish",
                    callback_data=ClassCB(action="view", class_id=classroom.id).pack(),
                ),
            ],
        ]
    )
    await safe_edit(
        callback,
        f"⚠️ <b>Haqiqatan ham «{uz.escape(classroom.name)}» guruhini o'chirmoqchimisiz?</b>\n\n"
        f"Guruh o'chirilganda unga a'zo bo'lgan o'quvchilar ro'yxati tozalanadi, "
        f"biriktirilgan testlar esa o'chmaydi (barchaga ochiq holatga o'tadi).",
        reply_markup=kb,
    )


@router.callback_query(ClassCB.filter(F.action == "delete"))
async def delete_classroom(
    callback: CallbackQuery,
    callback_data: ClassCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Guruhni o'chirish."""
    classroom = await _load_owned_classroom(session, callback_data.class_id, user)
    if classroom is None:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    cls_repo = ClassroomRepository(session)
    await cls_repo.delete(classroom)
    await session.commit()

    await safe_answer(callback, "🗑 Guruh o'chirildi.", alert=True)
    await open_classrooms_list(callback, user, session)
