"""
Savollar yechimlari va tushuntirishlari handlerlari.

O'quvchilar xato qilgan yoki qiziqqan savollarining batafsil yechimini
ko'ra oladilar, o'qituvchilar esa yechim matni yoki rasmini biriktira oladilar.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import IsRegistered
from apps.bot.keyboards.callbacks import ExplainCB
from apps.bot.keyboards.inline import (
    explanations_list_keyboard,
    home_keyboard,
    simple_back_keyboard,
)
from apps.bot.states import ExplanationEdit
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.exceptions import TestLabError
from core.logging import get_logger
from modules.assessment.service import AssessmentService
from modules.catalog.service import CatalogService
from modules.identity.models import User

log = get_logger(__name__)

router = Router(name="explanations")
router.message.filter(IsRegistered())
router.callback_query.filter(IsRegistered())


@router.callback_query(ExplainCB.filter(F.action == "list"))
async def list_explanations(
    callback: CallbackQuery,
    callback_data: ExplainCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Testdagi barcha savollar yechimlari ro'yxati."""
    await safe_answer(callback)

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)
    if test is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    explanations = await catalog.get_explanations(test.id)
    q_count = len(test.answer_key) if test.answer_key else test.questions_count

    await safe_edit(
        callback,
        f"💡 <b>SAVOLLAR YECHIMLARI VA IZOHLAR</b>\n"
        f"{uz.LINE}\n\n"
        f"📝 <b>Test:</b> {uz.escape(test.title)} (№{test.number})\n"
        f"❓ Savollar soni: <b>{q_count} ta</b>\n"
        f"✅ Yechimi kiritilgan: <b>{len(explanations)} ta</b>\n\n"
        f"<i>Kerakli savol raqamini tanlang:</i>",
        reply_markup=explanations_list_keyboard(test.id, q_count, explanations),
    )


@router.callback_query(ExplainCB.filter(F.action == "view"))
async def view_explanation(
    callback: CallbackQuery,
    callback_data: ExplainCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Bitta savol yechimini yoki umumiy yechim faylini ko'rish."""
    await safe_answer(callback)

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)
    if test is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    explanations = await catalog.get_explanations(test.id)
    explanation = explanations.get(callback_data.q_num)

    # Agar 0-savol (butun test uchun umumiy yechim fayli/videosi) bo'lsa:
    if callback_data.q_num == 0:
        if explanation and explanation.media_file_id:
            bot = callback.bot
            if bot:
                cap = f"📁 <b>{uz.escape(test.title)} — to'liq yechimlar</b>\n\n{uz.escape(explanation.explanation_text or '')}"
                try:
                    if explanation.media_type == "document":
                        await bot.send_document(chat_id=callback.from_user.id, document=explanation.media_file_id, caption=cap)
                    elif explanation.media_type == "video":
                        await bot.send_video(chat_id=callback.from_user.id, video=explanation.media_file_id, caption=cap)
                    elif explanation.media_type == "photo":
                        await bot.send_photo(chat_id=callback.from_user.id, photo=explanation.media_file_id, caption=cap)
                    await safe_answer(callback, "✅ Yechim yuborildi!")
                    return
                except Exception as err:
                    log.warning("Yechim faylini yuborishda xato: %s", err)
        await safe_answer(callback, "Ushbu test uchun to'liq yechim fayli yuklanmagan.", alert=True)
        return

    # Muayyan savol uchun yechim
    if explanation and explanation.media_file_id:
        bot = callback.bot
        if bot:
            cap = f"💡 <b>{callback_data.q_num}-savol yechimi:</b>\n\n{uz.escape(explanation.explanation_text or '')}"
            try:
                if explanation.media_type == "document":
                    await bot.send_document(chat_id=callback.from_user.id, document=explanation.media_file_id, caption=cap)
                elif explanation.media_type == "video":
                    await bot.send_video(chat_id=callback.from_user.id, video=explanation.media_file_id, caption=cap)
                elif explanation.media_type == "photo":
                    await bot.send_photo(chat_id=callback.from_user.id, photo=explanation.media_file_id, caption=cap)
            except Exception as err:
                log.warning("Savol yechimi mediasini yuborishda xato: %s", err)

    # O'quvchining bu savol bo'yicha xatosi bormi?
    assessment = AssessmentService(session)
    mistakes = await assessment.get_mistakes(user.id)
    my_mistake = None
    for m in mistakes:
        if m.test_id == test.id and m.question_number == callback_data.q_num:
            my_mistake = m
            break

    text = uz.explanation_view_text(test, callback_data.q_num, explanation, my_mistake=my_mistake)
    q_count = len(test.answer_key) if test.answer_key else test.questions_count
    await safe_edit(
        callback,
        text,
        reply_markup=explanations_list_keyboard(test.id, q_count, explanations),
    )


@router.callback_query(ExplainCB.filter(F.action == "edit"))
async def start_add_explanation(
    callback: CallbackQuery,
    callback_data: ExplainCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """O'qituvchi yechim qo'shishni boshlaydi."""
    await safe_answer(callback)

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)
    if test is None or (test.author_id != user.id and not user.is_admin):
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await state.set_state(ExplanationEdit.waiting_text)
    await state.update_data(test_id=test.id)

    if callback.message:
        await callback.message.answer(
            f"💡 <b>YECHIMLAR VA IZOHLAR BIRIKTIRISH</b>\n"
            f"{uz.LINE}\n\n"
            f"Siz test uchun quyidagi formatlarda yechim yuklashingiz mumkin:\n\n"
            f"📄 <b>Hujjat / Fayl:</b>\n"
            f"• <code>.pdf</code>, <code>.docx</code> yoki <code>.txt</code> faylini yuboring.\n"
            f"• (Butun test yechimlari uchun to'g'ridan-to'g'ri yuboring, yoki izohida savol raqamini yozing).\n\n"
            f"🎬 <b>Video yechim:</b>\n"
            f"• Yechim videosini yuboring.\n\n"
            f"🖼 <b>Rasm / Qo'lyozma:</b>\n"
            f"• Yechim suratini yuboring.\n\n"
            f"✍️ <b>Matnli yechim:</b>\n"
            f"• <code>1. Nyutonning 2-qonuni bo'yicha... \n2. Keyingi savol...</code>\n\n"
            f"<i>Bekor qilish uchun /cancel yuboring.</i>"
        )


@router.message(ExplanationEdit.waiting_text, F.document)
async def save_explanation_document(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Hujjat (PDF, DOCX, TXT) ko'rinishidagi yechimni saqlash."""
    data = await state.get_data()
    test_id = data.get("test_id")
    if not test_id or not message.document:
        await state.clear()
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(test_id)
    if test is None:
        await state.clear()
        return

    caption = (message.caption or "").strip()
    import re
    match = re.search(r"(\d{1,3})", caption)
    q_num = int(match.group(1)) if match else 0

    desc = caption or message.document.file_name or "Test yechimlari hujjati"
    await catalog.set_explanation(
        test,
        user,
        question_number=q_num,
        text=desc,
        media_file_id=message.document.file_id,
        media_type="document",
    )
    await state.clear()

    target_str = f"{q_num}-savolga" if q_num > 0 else "testning umumiy yechimlari bo'limiga"
    await message.answer(
        f"✅ <b>Hujjat ({message.document.file_name}) muvaffaqiyatli saqlandi!</b>\n\n"
        f"Fayl {target_str} biriktirildi. O'quvchilar uni «💡 Yechimlar / Izohlar» bo'limidan yuklab olishlari mumkin.",
        reply_markup=home_keyboard(),
    )


@router.message(ExplanationEdit.waiting_text, F.video)
async def save_explanation_video(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Video ko'rinishidagi yechimni saqlash."""
    data = await state.get_data()
    test_id = data.get("test_id")
    if not test_id or not message.video:
        await state.clear()
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(test_id)
    if test is None:
        await state.clear()
        return

    caption = (message.caption or "").strip()
    import re
    match = re.search(r"(\d{1,3})", caption)
    q_num = int(match.group(1)) if match else 0

    desc = caption or "Test yechimlari videosi"
    await catalog.set_explanation(
        test,
        user,
        question_number=q_num,
        text=desc,
        media_file_id=message.video.file_id,
        media_type="video",
    )
    await state.clear()

    target_str = f"{q_num}-savolga" if q_num > 0 else "testning umumiy yechimlari bo'limiga"
    await message.answer(
        f"✅ <b>Yechim videosi muvaffaqiyatli saqlandi!</b>\n\n"
        f"Video {target_str} biriktirildi. O'quvchilar uni «💡 Yechimlar / Izohlar» bo'limidan ko'rishlari mumkin.",
        reply_markup=home_keyboard(),
    )


@router.message(ExplanationEdit.waiting_text, F.photo)
async def save_explanation_photo(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Rasm ko'rinishidagi yechimni saqlash."""
    data = await state.get_data()
    test_id = data.get("test_id")
    if not test_id or not message.photo:
        await state.clear()
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(test_id)
    if test is None:
        await state.clear()
        return

    caption = (message.caption or "").strip()
    import re
    match = re.search(r"(\d{1,3})", caption)
    q_num = int(match.group(1)) if match else 0

    desc = caption or "Test yechimi rasmi"
    await catalog.set_explanation(
        test,
        user,
        question_number=q_num,
        text=desc,
        media_file_id=message.photo[-1].file_id,
        media_type="photo",
    )
    await state.clear()

    target_str = f"{q_num}-savolga" if q_num > 0 else "testning umumiy yechimlari bo'limiga"
    await message.answer(
        f"✅ <b>Yechim rasmi muvaffaqiyatli saqlandi!</b>\n\n"
        f"Rasm {target_str} biriktirildi.",
        reply_markup=home_keyboard(),
    )


@router.message(ExplanationEdit.waiting_text, F.text)
async def save_explanation(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """O'qituvchi yuborgan yechim matnini saqlash."""
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("✖️ Bekor qilindi.")
        return

    data = await state.get_data()
    test_id = data.get("test_id")
    if not test_id:
        await state.clear()
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(test_id)
    if test is None:
        await state.clear()
        return

    # Matndan savol raqamlari va yechimlarni ajratib olish
    lines = (message.text or "").strip().split("\n")
    saved_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        import re
        match = re.match(r"^(\d{1,3})[\.\)\:\-]\s*(.+)$", line)
        if match:
            q_num = int(match.group(1))
            expl_text = match.group(2).strip()
            await catalog.set_explanation(test, user, q_num, expl_text)
            saved_count += 1
        elif saved_count == 0 and len(lines) == 1:
            await catalog.set_explanation(test, user, 1, line)
            saved_count = 1

    await state.clear()
    await message.answer(
        f"✅ <b>{saved_count} ta savolga yechim biriktirildi!</b>\n\n"
        f"O'quvchilar testni yechgach, ushbu yechimlarni ko'ra oladilar.",
        reply_markup=home_keyboard(),
    )
