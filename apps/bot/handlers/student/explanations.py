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
from apps.bot.keyboards.callbacks import AppealCB, ExplainCB
from apps.bot.keyboards.inline import (
    appeal_teacher_reply_keyboard,
    explanations_list_keyboard,
    home_keyboard,
    simple_back_keyboard,
    single_explanation_keyboard,
)
from apps.bot.states import (
    ExplanationEdit,
    QuestionAppealState,
    TeacherAppealReplyState,
)
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
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

    from modules.assessment.repository import AttemptRepository

    is_privileged = test.author_id == user.id or user.is_admin
    if not is_privileged:
        finished_count = await AttemptRepository(session).count_by_user_and_test(user.id, test.id)
        if finished_count == 0:
            await safe_answer(
                callback,
                "🔒 Savollar yechimini ko'rish uchun avval ushbu testni topshirishingiz kerak!",
                alert=True,
            )
            return

        if not test.show_answers or (test.ends_at is not None and not test.already_ended):
            from core.datetime_utils import fmt_datetime

            msg = "🔒 Ushbu test hali yakunlanmagan. To'liq yechimlar va tushuntirishlar "
            if test.ends_at:
                msg += f"test muddati tugagach ({fmt_datetime(test.ends_at)}) ochiladi."
            else:
                msg += "test yakunlangach ochiladi."
            await safe_answer(callback, msg, alert=True)
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

    from modules.assessment.repository import AttemptRepository

    is_privileged = test.author_id == user.id or user.is_admin
    if not is_privileged:
        finished_count = await AttemptRepository(session).count_by_user_and_test(user.id, test.id)
        if finished_count == 0:
            await safe_answer(
                callback,
                "🔒 Savol yechimini ko'rish uchun avval ushbu testni topshirishingiz kerak!",
                alert=True,
            )
            return

        if not test.show_answers or (test.ends_at is not None and not test.already_ended):
            from core.datetime_utils import fmt_datetime

            msg = "🔒 Ushbu test hali yakunlanmagan. To'liq yechimlar va tushuntirishlar "
            if test.ends_at:
                msg += f"test muddati tugagach ({fmt_datetime(test.ends_at)}) ochiladi."
            else:
                msg += "test yakunlangach ochiladi."
            await safe_answer(callback, msg, alert=True)
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
    await safe_edit(
        callback,
        text,
        reply_markup=single_explanation_keyboard(
            test.id,
            callback_data.q_num,
            from_retake=bool(my_mistake or mistakes),
        ),
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


# ======================================================================
#  SAVOL BO'YICHA E'TIROZ (APELLYATSIYA)
# ======================================================================

@router.callback_query(AppealCB.filter(F.action == "ask"))
async def start_question_appeal(
    callback: CallbackQuery,
    callback_data: AppealCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """O'quvchi savol bo'yicha e'tiroz yozishni boshlaydi."""
    await safe_answer(callback)

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)
    if test is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    is_privileged = test.author_id == user.id or user.is_admin
    if not is_privileged:
        from modules.assessment.repository import AttemptRepository

        finished_count = await AttemptRepository(session).count_by_user_and_test(user.id, test.id)
        if finished_count == 0:
            await safe_answer(
                callback,
                "⚠️ E'tiroz yo'llash uchun avval ushbu testni topshirgan bo'lishingiz kerak.",
                alert=True,
            )
            return

    await state.set_state(QuestionAppealState.waiting_for_text)
    await state.update_data(test_id=test.id, q_num=callback_data.q_num)

    q_text = f"{callback_data.q_num}-savol" if callback_data.q_num > 0 else "Umumiy test"
    if callback.message:
        await callback.message.answer(
            f"📩 <b>O'qituvchiga murojaat / e'tiroz yo'llash</b>\n"
            f"{uz.LINE}\n\n"
            f"📝 <b>Test:</b> {uz.escape(test.title)} (№{test.number})\n"
            f"❓ <b>Savol:</b> {q_text}\n\n"
            f"Ushbu savol yuzasidan e'tirozingiz, fikringiz yoki tushunmagan joyingizni batafsil yozib yuboring:\n"
            f"<i>(Masalan: «Domla, 5-savolda javob C emas, B chiqadi, chunki...»)</i>\n\n"
            f"Bekor qilish: /cancel",
            reply_markup=simple_back_keyboard(),
        )


@router.message(QuestionAppealState.waiting_for_text, F.text)
async def submit_question_appeal(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """O'quvchi e'tiroz matnini yuborganda uni saqlash va o'qituvchiga yetkazish."""
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("✖️ Murojaat bekor qilindi.", reply_markup=home_keyboard())
        return

    data = await state.get_data()
    test_id = data.get("test_id")
    q_num = data.get("q_num", 0)
    await state.clear()

    if not test_id:
        return

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(test_id)
    if test is None:
        await message.answer(uz.NOT_FOUND, reply_markup=home_keyboard())
        return

    appeal_text = (message.text or "").strip()
    appeal = await catalog.create_appeal(
        test_id=test.id,
        question_number=q_num,
        user_id=user.id,
        text=appeal_text,
    )

    # Test muallifiga (o'qituvchiga) Telegram xabarnoma yuboramiz
    if test.author_id and test.author_id != user.id:
        from modules.identity.repository import UserRepository
        author = await UserRepository(session).get(test.author_id)
        if author and author.telegram_id and message.bot:
            q_info = f"{q_num}-savol" if q_num > 0 else "Umumiy test"
            notify_text = (
                f"📩 <b>YANGI SAVOL MUROJAATI / APELLYATSIYA</b>\n"
                f"{uz.LINE}\n\n"
                f"📝 <b>Test:</b> {uz.escape(test.title)} (№{test.number})\n"
                f"❓ <b>Savol:</b> {q_info}\n"
                f"👤 <b>O'quvchi:</b> {uz.escape(user.full_name)} (@{user.username or '—'})\n\n"
                f"💬 <b>Murojaat matni:</b>\n"
                f"«<i>{uz.escape(appeal_text)}</i>»\n"
                f"{uz.LINE}\n"
                f"💡 <i>Quyidagi tugma orqali o'quvchiga darhol javob yo'llashingiz mumkin:</i>"
            )
            try:
                await message.bot.send_message(
                    chat_id=author.telegram_id,
                    text=notify_text,
                    reply_markup=appeal_teacher_reply_keyboard(
                        appeal_id=appeal.id,
                        student_id=user.telegram_id,
                        test_id=test.id,
                        q_num=q_num,
                    ),
                )
            except Exception as notify_err:
                log.warning("O'qituvchiga murojaat xabari bormadi: %s", notify_err)

    await message.answer(
        "✅ <b>Murojaatingiz qabul qilindi!</b>\n\n"
        "Savolingiz test muallifiga yetkazildi. O'qituvchi javob berishi bilan bot sizga bildirishnoma yuboradi.",
        reply_markup=home_keyboard(),
    )


@router.callback_query(AppealCB.filter(F.action == "reply"))
async def start_teacher_appeal_reply(
    callback: CallbackQuery,
    callback_data: AppealCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """O'qituvchi o'quvchiga javob qaytarishni boshlaydi."""
    await safe_answer(callback)

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)
    if test is None or (test.author_id != user.id and not user.is_admin):
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await state.set_state(TeacherAppealReplyState.waiting_for_reply)
    await state.update_data(
        appeal_id=callback_data.appeal_id,
        student_id=callback_data.target_user_id,
        test_id=test.id,
        q_num=callback_data.q_num,
    )

    q_info = f"{callback_data.q_num}-savol" if callback_data.q_num > 0 else "test"
    if callback.message:
        await callback.message.answer(
            f"✍️ <b>O'quvchiga javob qaytarish</b>\n"
            f"{uz.LINE}\n\n"
            f"Test №{test.number}, {q_info} yuzasidan o'quvchiga tushuntirishingiz yoki javobingizni yozib yuboring:\n\n"
            f"<i>Bekor qilish: /cancel</i>"
        )


@router.message(TeacherAppealReplyState.waiting_for_reply, F.text)
async def submit_teacher_appeal_reply(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """O'qituvchi yozgan javobni o'quvchiga yuborish."""
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("✖️ Javob berish bekor qilindi.", reply_markup=home_keyboard())
        return

    data = await state.get_data()
    appeal_id = data.get("appeal_id")
    student_id = data.get("student_id")
    test_id = data.get("test_id")
    q_num = data.get("q_num", 0)
    await state.clear()

    reply_text = (message.text or "").strip()

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(test_id) if test_id else None
    test_title = test.title if test else "Test"
    test_num = test.number if test else ""

    if appeal_id:
        await catalog.reply_appeal(appeal_id, reply_text)

    # O'quvchiga Telegram orqali javob yuboramiz
    if student_id and message.bot:
        q_info = f"{q_num}-savol" if q_num > 0 else "Test"
        student_msg = (
            f"👨‍🏫 <b>O'QITUVCHIDAN JAVOB KELDI</b>\n"
            f"{uz.LINE}\n\n"
            f"📝 <b>Test:</b> {uz.escape(test_title)} (№{test_num})\n"
            f"❓ <b>Mavzu:</b> {q_info} yuzasidan murojaatingiz\n"
            f"👤 <b>O'qituvchi:</b> {uz.escape(user.full_name)}\n\n"
            f"💬 <b>O'qituvchi javobi:</b>\n"
            f"«<i>{uz.escape(reply_text)}</i>»\n"
            f"{uz.LINE}"
        )
        try:
            await message.bot.send_message(
                chat_id=student_id,
                text=student_msg,
                reply_markup=home_keyboard(),
            )
        except Exception as send_err:
            log.warning("O'quvchiga javob bormadi: %s", send_err)

    await message.answer(
        "✅ <b>Javobingiz o'quvchiga muvaffaqiyatli yuborildi!</b>",
        reply_markup=home_keyboard(),
    )

