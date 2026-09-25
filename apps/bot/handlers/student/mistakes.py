"""
Xatolar ustida ishlash (Personal Retake / Xatolar daftari).

O'quvchi avval yechgan testlarida xato qilgan savollarni bu yerda
alohida qayta yechib, o'z bilimini mustahkamlaydi va xatoni to'g'rilaydi.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
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
from apps.bot.utils import safe_answer, safe_edit, send_media_group
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
    state: FSMContext,
) -> None:
    """Xatolar daftari bosh ekrani."""
    await safe_answer(callback)
    await state.update_data(mistake_media_test_id=None)

    assessment = AssessmentService(session)
    mistakes = await assessment.get_mistakes(user.id)

    await safe_edit(
        callback,
        uz.mistakes_hub_text(mistakes),
        reply_markup=mistakes_hub_keyboard(has_mistakes=bool(mistakes)),
    )


@router.callback_query(MistakeCB.filter(F.action.in_({"retake", "skip"})))
async def start_retake(
    callback: CallbackQuery,
    callback_data: MistakeCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Xatolarni qayta yechish: navbatdagi xatoni ko'rsatish."""
    await safe_answer(callback)

    assessment = AssessmentService(session)
    mistakes = await assessment.get_mistakes(user.id)

    if not mistakes:
        await state.update_data(mistake_media_test_id=None)
        await safe_edit(
            callback,
            "🎉 <b>Barcha xatolar to'g'rilandi!</b>\n\n"
            "Xatolar daftaringizda boshqa savol qolmadi. Ajoyib natija!",
            reply_markup=home_keyboard(),
        )
        return

    # O'tkazib yuborish (skip) bo'lsa navbatdagi xatoni tanlash
    target_idx = 0
    if callback_data.action == "skip" and callback_data.q_num:
        for idx, m in enumerate(mistakes):
            if m.test_id == callback_data.test_id and m.question_number == callback_data.q_num:
                target_idx = (idx + 1) % len(mistakes)
                break

    current = mistakes[target_idx]
    test = current.test

    catalog = CatalogService(session)
    media = await catalog.list_media(test) if test else []
    has_media = bool(media)

    card_text = (
        f"🎯 <b>XATOLAR USTIDA ISHLASH</b> · {len(mistakes)} ta qoldi\n"
        f"{uz.LINE}\n\n"
        f"📝 <b>Fan / Test:</b> {uz.escape(test.title if test else f'№{current.test_id}')}\n"
        f"❓ <b>Savol raqami:</b> #{current.question_number}\n"
        f"❌ <b>Avvalgi xato javobingiz:</b> {current.given_answer}\n\n"
        f"💡 Qaytadan o'ylab ko'ring va to'g'ri variantni tanlang 👇"
    )

    data = await state.get_data()
    last_media_test_id = data.get("mistake_media_test_id")

    # Agar testning rasmlari/fayllari bo'lsa va bu test uchun hali yuborilmagan bo'lsa
    if has_media and last_media_test_id != current.test_id:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await send_media_group(callback.message, media, user=user, protect_content=True)
        await state.update_data(mistake_media_test_id=current.test_id)
        await callback.message.answer(
            card_text,
            reply_markup=mistake_question_keyboard(
                current.test_id,
                current.question_number,
                has_media=True,
            ),
        )
        return

    # Agar rasmlar allaqachon yuborilgan bo'lsa yoki rasm bo'lmasa — kartani tahrirlaymiz
    await safe_edit(
        callback,
        card_text,
        reply_markup=mistake_question_keyboard(
            current.test_id,
            current.question_number,
            has_media=has_media,
        ),
    )


@router.callback_query(MistakeCB.filter(F.action == "sheet"))
async def send_mistake_sheet(
    callback: CallbackQuery,
    callback_data: MistakeCB,
    user: User,
    session: AsyncSession,
) -> None:
    """O'quvchi 'Test varaqasi' tugmasini bosganda test materiallarini yuborish."""
    await safe_answer(callback, "🖼 Test varaqasi yuborilmoqda...")

    catalog = CatalogService(session)
    test = await catalog.tests.get_full(callback_data.test_id)
    if not test:
        await safe_answer(callback, uz.NOT_FOUND, alert=True)
        return

    media = await catalog.list_media(test)
    if not media:
        await safe_answer(callback, "Ushbu test uchun rasm yoki fayl yuklanmagan.", alert=True)
        return

    await send_media_group(callback.message, media, user=user, protect_content=True)


@router.callback_query(MistakeCB.filter(F.action == "answer"))
async def check_retake_answer(
    callback: CallbackQuery,
    callback_data: MistakeCB,
    user: User,
    session: AsyncSession,
    state: FSMContext,
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
        await start_retake(
            callback,
            MistakeCB(action="retake"),
            user,
            session,
            state,
        )
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
        await start_retake(
            callback,
            MistakeCB(action="retake"),
            user,
            session,
            state,
        )
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
    state: FSMContext,
) -> None:
    """Barcha xatolarni tozalash."""
    await safe_answer(callback)
    await state.update_data(mistake_media_test_id=None)

    assessment = AssessmentService(session)
    count = await assessment.clear_mistakes(user.id)

    await safe_edit(
        callback,
        f"🧹 <b>Xatolar daftari tozalandi!</b>\n\n"
        f"Jami <b>{count} ta</b> xato o'chirildi.",
        reply_markup=home_keyboard(),
    )
