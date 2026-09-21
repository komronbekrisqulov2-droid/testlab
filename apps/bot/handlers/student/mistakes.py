"""
Xatolar ustida ishlash (Personal Retake / Xatolar daftari).

O'quvchi avval yechgan testlarida xato qilgan savollarni bu yerda
alohida qayta yechib, o'z bilimini mustahkamlaydi va xatoni to'g'rilaydi.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.filters import IsRegistered
from apps.bot.keyboards.callbacks import MistakeCB
from apps.bot.keyboards.inline import (
    home_keyboard,
    mistake_question_keyboard,
    mistakes_hub_keyboard,
)
from apps.bot.texts import uz
from apps.bot.utils import safe_answer, safe_edit
from core.logging import get_logger
from modules.assessment.service import AssessmentService
from modules.catalog.service import CatalogService
from modules.identity.models import User

log = get_logger(__name__)

router = Router(name="student_mistakes")
router.message.filter(IsRegistered())
router.callback_query.filter(IsRegistered())


@router.callback_query(MistakeCB.filter(F.action == "hub"))
async def open_mistakes_hub(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Xatolar daftari bosh ekrani."""
    await safe_answer(callback)

    assessment = AssessmentService(session)
    mistakes = await assessment.get_mistakes(user.id)

    await safe_edit(
        callback,
        uz.mistakes_hub_text(mistakes),
        reply_markup=mistakes_hub_keyboard(has_mistakes=bool(mistakes)),
    )


@router.callback_query(MistakeCB.filter(F.action == "retake"))
async def start_retake(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Xatolarni qayta yechish: navbatdagi xatoni ko'rsatish."""
    await safe_answer(callback)

    assessment = AssessmentService(session)
    mistakes = await assessment.get_mistakes(user.id)

    if not mistakes:
        await safe_edit(
            callback,
            "🎉 <b>Barcha xatolar to'g'rilandi!</b>\n\n"
            "Xatolar daftaringizda boshqa savol qolmadi. Ajoyib natija!",
            reply_markup=home_keyboard(),
        )
        return

    # Navbatdagi xato
    current = mistakes[0]
    test = current.test

    card_text = (
        f"🎯 <b>XATOLAR USTIDA ISHLASH</b> · {len(mistakes)} ta qoldi\n"
        f"{uz.LINE}\n\n"
        f"📝 <b>Fan / Test:</b> {uz.escape(test.title if test else f'№{current.test_id}')}\n"
        f"❓ <b>Savol raqami:</b> #{current.question_number}\n"
        f"❌ <b>Avvalgi xato javobingiz:</b> {current.given_answer}\n\n"
        f"💡 Qaytadan o'ylab ko'ring va to'g'ri variantni tanlang 👇"
    )

    await safe_edit(
        callback,
        card_text,
        reply_markup=mistake_question_keyboard(current.test_id, current.question_number),
    )


@router.callback_query(MistakeCB.filter(F.action == "answer"))
async def check_retake_answer(
    callback: CallbackQuery,
    callback_data: MistakeCB,
    user: User,
    session: AsyncSession,
) -> None:
    """O'quvchi xatosini qayta belgiladi."""
    assessment = AssessmentService(session)
    mistakes = await assessment.get_mistakes(user.id)

    target = None
    for m in mistakes:
        if m.test_id == callback_data.test_id and m.question_number == callback_data.q_num:
            target = m
            break

    if target is None:
        await safe_answer(callback, "Bu savol allaqachon to'g'rilangan yoki topilmadi.", alert=True)
        await start_retake(callback, user, session)
        return

    chosen = (callback_data.choice or "").upper()
    correct = target.correct_answer.upper()

    if chosen == correct:
        # To'g'ri topildi!
        await assessment.resolve_mistake(user.id, target.test_id, target.question_number)
        user.xp += 3  # Qayta yechganlik uchun rag'batlantiruvchi XP
        await session.commit()

        await safe_answer(
            callback,
            f"🎉 BARAKALLA! To'g'ri javob: {correct}! (+3 XP)",
            alert=True,
        )
        # Keyingi savolga o'tish
        await start_retake(callback, user, session)
    else:
        await safe_answer(
            callback,
            f"❌ Noto'g'ri! Siz tanlagan {chosen} varianti ham xato. Qaytadan urinib ko'ring yoki yechimni ko'ring.",
            alert=True,
        )


@router.callback_query(MistakeCB.filter(F.action == "clear"))
async def clear_all_mistakes(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Barcha xatolarni tozalash."""
    await safe_answer(callback)

    assessment = AssessmentService(session)
    count = await assessment.clear_mistakes(user.id)

    await safe_edit(
        callback,
        f"🧹 <b>Xatolar daftari tozalandi!</b>\n\n"
        f"Jami <b>{count} ta</b> xato o'chirildi.",
        reply_markup=home_keyboard(),
    )
