"""
Natijani ko'rsatish: rasmli kartochka + sertifikat.

Nega rasm? Matnli natijani hech kim ulashmaydi. Kartochka esa story'ga
tashlanadi, do'stga yuboriladi — **har bir ulashish bepul reklama**.

Rasm chizib bo'lmasa (shrift yo'q, xotira yetmadi) natija baribir
matn ko'rinishida yuboriladi — o'quvchi natijasiz qolmaydi.
"""

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.keyboards.callbacks import AdminCB, AttemptCB, CertCB, MenuCB, PeopleCB, TestCB
from apps.bot.keyboards.inline import (
    attempt_detail_keyboard,
    home_button,
    home_keyboard,
    participants_keyboard,
    result_keyboard,
)
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.exceptions import TestLabError
from core.logging import get_logger
from core.security.permissions import Permission
from modules.assessment.repository import AttemptRepository
from modules.certification.service import CertificateService
from modules.catalog.models import TestStatus
from modules.catalog.service import CatalogService
from modules.identity.models import User
from modules.media import result_card

log = get_logger(__name__)
router = Router(name="student_result")

HISTORY_SIZE = 6


async def send_result(
    message: Message,
    submit,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Natijani yuboradi: tezkor va to'liq HTML natija + boshqaruv tugmalari.

    Rasmli kartochka talab bo'yicha (alohida tugma orqali) orqa fonda
    chiziladi — bu orqali natija xabari 5 barobar tezroq (50-80 ms) yetkaziladi
    va botning asosiy asyncio oqimi og'ir Pillow ishlaridan ozod qilinadi.
    """
    certificates = CertificateService(session)
    can_certify, _ = await certificates.can_issue(submit.attempt, submit.test)

    hide_keys = not submit.test.show_answers or (
        submit.test.ends_at is not None and not submit.test.already_ended
    )

    caption = uz.result(submit, hide_keys=hide_keys)
    keyboard = result_keyboard(
        submit.test.id,
        attempt_id=submit.attempt.id,
        can_get_certificate=can_certify,
        hide_analysis=hide_keys,
    )

    await message.answer(caption, reply_markup=keyboard)


@router.callback_query(AttemptCB.filter(F.action == "card"))
async def send_result_card(
    callback: CallbackQuery,
    callback_data: AttemptCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Rasmli natija kartochkasini so'rov bo'yicha alohida thread'da chizadi va yuboradi."""
    if callback.message is None:
        return

    await safe_answer(callback, "🖼 Natija kartochkasi tayyorlanmoqda...")

    attempts = AttemptRepository(session)
    attempt = await attempts.get_full(callback_data.attempt_id)

    if attempt is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    if attempt.user_id != user.id and not user.is_admin:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    history = await attempts.recent_percentages(user.id, limit=HISTORY_SIZE)
    rank, participants = await attempts.rank_in_test(attempt)

    card_data = result_card.ResultCardData(
        student_name=user.full_name,
        test_title=attempt.test.title if attempt.test else f"Test #{attempt.test_id}",
        test_number=attempt.test.number if attempt.test else attempt.test_id,
        percentage=attempt.percentage,
        correct=attempt.correct_answers,
        total=attempt.max_score,
        wrong=attempt.wrong_answers,
        skipped=attempt.unanswered,
        grade=attempt.grade or "F",
        rank=rank,
        participants=participants,
        passed=attempt.is_passed,
        pass_score=attempt.test.pass_score if attempt.test else 60,
        history=tuple(history),
        streak=user.streak_days,
    )

    # Pillow orqali 1080x1080 rasmni alohida Worker Thread'da chizamiz (Main thread qotmaydi)
    try:
        card = await asyncio.to_thread(result_card.render, card_data)
    except Exception as error:
        log.exception("Natija kartochkasi chizilmadi: %s", error)
        await callback.message.answer("⚠️ Kartochka tayyorlashda xatolik yuz berdi.")
        return

    filename = f"natija_{card_data.test_number}_{int(card_data.percentage)}.png"
    await callback.message.answer_photo(
        photo=BufferedInputFile(card, filename=filename),
        caption=f"🎯 <b>{uz.escape(card_data.test_title)}</b> — rasmli natija kartochkangiz!",
    )


# ======================================================================
#  SERTIFIKAT
# ======================================================================

@router.callback_query(CertCB.filter(F.action == "hub"))
async def open_certificate_hub(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """O'quvchining barcha sertifikatlari va o'tgan testlari markazi."""
    await safe_answer(callback)

    attempts_repo = AttemptRepository(session)
    attempts_page = await attempts_repo.list_by_user(user.id, page=1, per_page=30)

    passed: list = []
    seen_tests: set[int] = set()
    for att in attempts_page.items:
        is_pass = att.is_passed or (att.test and att.percentage >= att.test.pass_score) or att.percentage >= 60
        if is_pass and att.test_id not in seen_tests:
            seen_tests.add(att.test_id)
            passed.append(att)

    builder = InlineKeyboardBuilder()

    if not passed:
        text = (
            f"🎓 <b>SERTIFIKATLAR MARKAZI</b>\n"
            f"{uz.LINE}\n\n"
            "ℹ️ <i>Sizda hali sertifikat olish uchun mos (o'tgan) natijalar topilmadi.</i>\n\n"
            "📌 <b>Sertifikat olish shartlari:</b>\n"
            "• Test topshirib, o'tish ballidan yuqori natija ko'rsatish (kamida 60%);\n"
            "• A+, A, B yoki C darajasiga erishish.\n\n"
            "💡 <i>Testlarni muvaffaqiyatli topshiring va o'z bilimingizni tasdiqlovchi rasmiy sertifikatlarga ega bo'ling!</i>"
        )
        builder.row(InlineKeyboardButton(text="📊 Natijalarim", callback_data=MenuCB(action="results").pack()))
        builder.row(home_button())
        await safe_edit(callback, text, reply_markup=builder.as_markup())
        return

    text = (
        f"🎓 <b>SERTIFIKATLAR MARKAZI</b>\n"
        f"{uz.LINE}\n\n"
        "Tabriklaymiz! Siz quyidagi testlarni muvaffaqiyatli topshirgansiz.\n"
        "Kerakli testni tanlang va o'z <b>rasmiy sertifikatingizni</b> yuklab oling:\n"
    )

    for att in passed:
        test_title = att.test.title if att.test else f"Test #{att.test_id}"
        grade_part = f" · {att.grade}" if att.grade else ""
        btn_text = f"📜 {test_title} ({att.percentage:g}%{grade_part})"
        builder.row(
            InlineKeyboardButton(
                text=btn_text,
                callback_data=CertCB(action="issue", attempt_id=att.id).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(text="📊 Natijalarim", callback_data=MenuCB(action="results").pack()),
        home_button(),
    )
    await safe_edit(callback, text, reply_markup=builder.as_markup())


@router.callback_query(CertCB.filter(F.action == "issue"))
async def issue_certificate(
    callback: CallbackQuery,
    callback_data: CertCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Sertifikat yaratadi va yuboradi."""
    if callback.message is None:
        return

    attempts = AttemptRepository(session)
    attempt = await attempts.get_full(callback_data.attempt_id)

    if attempt is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    if attempt.user_id != user.id:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    await safe_answer(callback, uz.CERTIFICATE_BUILDING)

    service = CertificateService(session)

    try:
        certificate = await service.issue(attempt, attempt.test, user)
    except TestLabError as error:
        await safe_answer(callback, error.message[:200], alert=True)
        return

    await _send_certificate(callback.message, certificate, service, session)


async def _send_certificate(
    message: Message,
    certificate,
    service: CertificateService,
    session: AsyncSession,
) -> None:
    """
    Sertifikatni yuboradi.

    Telegram'da saqlangan `file_id` bo'lsa qayta chizilmaydi — bu
    bir necha marta tezroq.
    """
    caption = uz.certificate_caption(certificate)
    keyboard = home_keyboard()

    #  --- Keshdan ---
    if certificate.file_id:
        try:
            await message.answer_photo(
                photo=certificate.file_id, caption=caption, reply_markup=keyboard
            )
            return
        except Exception as error:
            log.warning("Keshlangan sertifikat yuborilmadi: %s", error)

    #  --- Chizamiz (Worker thread orqali Event Loop qotmaydi) ---
    try:
        image = await asyncio.to_thread(service.render, certificate)
    except Exception as error:
        log.exception("Sertifikat chizilmadi: %s", error)
        await message.answer(
            "⚠️ Sertifikat tayyorlashda xatolik. Keyinroq urinib ko'ring."
        )
        return

    sent = await message.answer_photo(
        photo=BufferedInputFile(image, filename=service.filename(certificate)),
        caption=caption,
        reply_markup=keyboard,
    )

    #  Keyingi safar qayta chizmaslik uchun saqlaymiz
    if sent.photo:
        await service.certificates.save_file_ids(
            certificate, photo_file_id=sent.photo[-1].file_id
        )

    #  Yuqori sifatli nusxa — chop etish uchun
    try:
        await message.answer_document(
            document=BufferedInputFile(image, filename=service.filename(certificate)),
            caption="📄 Yuqori sifatli nusxa (chop etish uchun)",
        )
    except Exception as error:
        log.debug("Sertifikat hujjati yuborilmadi: %s", error)


# ======================================================================
#  URINISH TAHLILI VA SAVOLLARNI KO'RISH
# ======================================================================

@router.callback_query(AttemptCB.filter(F.action == "view"))
async def view_attempt_analysis(
    callback: CallbackQuery,
    callback_data: AttemptCB,
    user: User,
    session: AsyncSession,
) -> None:
    """O'quvchi yechgan testining savolma-savol to'liq tahlili."""
    await safe_answer(callback)

    attempts = AttemptRepository(session)
    attempt = await attempts.get_full(callback_data.attempt_id)

    if attempt is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    if attempt.user_id != user.id and not user.is_admin:
        await safe_answer(callback, uz.NO_PERMISSION, alert=True)
        return

    test = attempt.test
    if test and (not test.show_answers or (test.ends_at is not None and not test.already_ended)):
        from core.datetime_utils import fmt_datetime
        msg = "🔒 Ushbu test hali yakunlanmagan. To'g'ri kalitlar va savollar tahlili "
        if test.ends_at:
            msg += f"test muddati tugagach ({fmt_datetime(test.ends_at)}) ochiladi."
        else:
            msg += "test yakunlangach ochiladi."
        await safe_answer(callback, msg, alert=True)
        return

    from modules.catalog.service import CatalogService
    catalog = CatalogService(session)
    explanations = await catalog.get_explanations(attempt.test_id)

    from modules.assessment.service import AssessmentService
    mistakes = await AssessmentService(session).get_mistakes(user.id)
    has_mistakes = any(m.test_id == attempt.test_id for m in mistakes)

    certificates = CertificateService(session)
    can_certify, _ = await certificates.can_issue(attempt, attempt.test) if attempt.test else (False, "")

    text = uz.attempt_detail_text(attempt, explanations)
    keyboard = attempt_detail_keyboard(
        test_id=attempt.test_id,
        attempt_id=attempt.id,
        has_mistakes=has_mistakes,
        can_certify=can_certify,
        page=callback_data.page,
    )

    await safe_edit(callback, text, reply_markup=keyboard)


# ======================================================================
#  TESTNI ISHLAGANLAR RO'YXATI
# ======================================================================

@router.callback_query(PeopleCB.filter(F.action == "list"))
async def show_participants(
    callback: CallbackQuery,
    callback_data: PeopleCB,
    user: User,
    session: AsyncSession,
) -> None:
    """Testni ishlaganlar ro'yxati (reyting tartibida)."""
    await safe_answer(callback)

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)
    if test is None:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    # Qoralama bo'lsa va muallif/admin bo'lmasa ko'rsatmaymiz
    if test.status == TestStatus.DRAFT.value and test.author_id != user.id and not user.is_admin:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    attempts = AttemptRepository(session)
    per_page = 25
    page = await attempts.list_by_test(
        test.id,
        page=max(1, callback_data.page),
        per_page=per_page,
        by_rank=True,
    )

    if test.author_id == user.id:
        back = TestCB(action="manage", test_id=test.id).pack()
        can_excel = True
    elif user.can(Permission.RESULTS_VIEW_ANY):
        back = AdminCB(action="tests", page=1).pack()
        can_excel = True
    else:
        back = TestCB(action="open", test_id=test.id).pack()
        can_excel = False

    text = uz.participants_page(test, page, start=page.start_index)
    keyboard = participants_keyboard(
        test.id,
        page,
        back_callback=back,
        can_excel=can_excel,
    )

    await safe_edit(callback, text, reply_markup=keyboard)

