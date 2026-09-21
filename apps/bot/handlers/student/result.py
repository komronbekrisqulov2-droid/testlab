"""
Natijani ko'rsatish: rasmli kartochka + sertifikat.

Nega rasm? Matnli natijani hech kim ulashmaydi. Kartochka esa story'ga
tashlanadi, do'stga yuboriladi — **har bir ulashish bepul reklama**.

Rasm chizib bo'lmasa (shrift yo'q, xotira yetmadi) natija baribir
matn ko'rinishida yuboriladi — o'quvchi natijasiz qolmaydi.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.keyboards.callbacks import CertCB, MenuCB
from apps.bot.keyboards.inline import home_button, home_keyboard, result_keyboard
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.exceptions import TestLabError
from core.logging import get_logger
from modules.assessment.repository import AttemptRepository
from modules.certification.service import CertificateService
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
    Natijani yuboradi: kartochka rasmi + qisqa matn + tugmalar.

    `submit` — AssessmentService.SubmitResult
    """
    attempts = AttemptRepository(session)
    history = await attempts.recent_percentages(user.id, limit=HISTORY_SIZE)

    certificates = CertificateService(session)
    can_certify, _ = await certificates.can_issue(submit.attempt, submit.test)

    caption = uz.result(submit)
    keyboard = result_keyboard(
        submit.test.id,
        attempt_id=submit.attempt.id,
        can_get_certificate=can_certify,
    )

    #  --- Kartochka ---
    card = _render_card(submit, user, history)

    if card is None:
        #  Rasm chizilmadi — matn baribir yuboriladi
        await message.answer(caption, reply_markup=keyboard)
        return

    #  Telegram rasm izohi 1024 belgi bilan cheklangan.
    #  Uzun natija bo'lsa rasmni alohida, matnni alohida yuboramiz.
    if len(caption) <= 1024:
        await message.answer_photo(
            photo=BufferedInputFile(card, filename=_filename(submit)),
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await message.answer_photo(
            photo=BufferedInputFile(card, filename=_filename(submit)),
        )
        await message.answer(caption, reply_markup=keyboard)


def _render_card(submit, user: User, history: list[float]) -> bytes | None:
    """Kartochkani chizadi. Xato bo'lsa None (natija matn bilan ketadi)."""
    try:
        return result_card.render(result_card.ResultCardData(
            student_name=user.full_name,
            test_title=submit.test.title,
            test_number=submit.test.number,
            percentage=submit.percentage,
            correct=submit.correct,
            total=submit.attempt.max_score,
            wrong=submit.wrong,
            skipped=submit.skipped,
            grade=submit.grade,
            rank=submit.rank,
            participants=submit.participants,
            passed=submit.passed,
            pass_score=submit.test.pass_score,
            history=tuple(history),
            streak=user.streak_days,
        ))
    except Exception as error:
        log.exception("Natija kartochkasi chizilmadi: %s", error)
        return None


def _filename(submit) -> str:
    return f"natija_{submit.test.number}_{int(submit.percentage)}.png"


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

    #  --- Chizamiz ---
    try:
        image = service.render(certificate)
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
