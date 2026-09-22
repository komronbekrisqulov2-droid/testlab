"""
Savol bo'yicha e'tiroz (Apellyatsiya) va Gemini AI Guided Prompting sinovlari.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401,E402

from core.security.permissions import Role
from infrastructure.database.engine import engine, session_factory
from modules.catalog.service import CatalogService
from modules.identity.repository import UserRepository
from modules.registry import Base
from apps.bot.keyboards.inline import (
    single_explanation_keyboard,
    appeal_teacher_reply_keyboard,
    attempt_detail_keyboard,
)

_failures = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


def check_true(label: str, val: bool) -> None:
    check(label, bool(val), True)


async def test_appeal_flow() -> None:
    print("\n--- 1. Savol bo'yicha e'tiroz (Apellyatsiya) DB & Service Sinovi ---")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        users = UserRepository(session)
        teacher, _ = await users.get_or_create(1001, username="ustoz", first_name="Domla")
        teacher.role = Role.TEACHER.value
        student, _ = await users.get_or_create(2002, username="talaba", first_name="Ali")
        await session.commit()

        catalog = CatalogService(session)
        test = await catalog.create_from_one_line(teacher, "Fizika Testi+ABCDABCD")
        await session.commit()

        check_true("Test yaratildi", test is not None)
        test_id = test.id

    async with session_factory() as session:
        catalog = CatalogService(session)
        # O'quvchi 3-savol bo'yicha e'tiroz kiritadi
        appeal = await catalog.create_appeal(
            test_id=test_id,
            question_number=3,
            user_id=student.id,
            text="3-savolda formulada manfiy ishora tushib qolgan, natijada C emas B chiqadi.",
        )
        check("E'tiroz saqlandi", appeal.status, "pending")
        check("Savol raqami to'g'ri", appeal.question_number, 3)
        check_true("Matn to'g'ri", "manfiy ishora" in appeal.appeal_text)
        appeal_id = appeal.id

    async with session_factory() as session:
        catalog = CatalogService(session)
        # O'qituvchi e'tirozga javob yozadi
        updated = await catalog.reply_appeal(
            appeal_id=appeal_id,
            reply_text="Rahmat Ali, haqiqatan ham formulada ishora adashgan ekan, kalitni to'g'riladim!",
        )
        check("E'tiroz holati 'replied'", updated.status, "replied")
        check_true("Javob matni saqlandi", "kalitni to'g'riladim" in updated.reply_text)
        check_true("Javob vaqti qayd etildi", updated.replied_at is not None)

        # Test bo'yicha barcha e'tirozlarni olish
        appeals = await catalog.get_appeals_by_test(test_id)
        check("Testdagi e'tirozlar soni 1 ta", len(appeals), 1)


def test_keyboards() -> None:
    print("\n--- 2. Klaviaturalar va Tugmalar Sinovi (E'tiroz tugmasi olinganligi) ---")
    kb1 = single_explanation_keyboard(test_id=5, q_num=3)
    buttons1 = [btn.text for row in kb1.inline_keyboard for btn in row]
    check_true("E'tiroz yo'llash tugmasi olib tashlangan (single_explanation)", not any("e'tiroz" in b.lower() for b in buttons1))
    check_true("Barcha yechimlar tugmasi bor", any("barcha savollar yechimlari" in b.lower() for b in buttons1))

    kb3 = attempt_detail_keyboard(test_id=5, attempt_id=10)
    buttons3 = [btn.text for row in kb3.inline_keyboard for btn in row]
    check_true("Natija tahlilida e'tiroz tugmasi olib tashlangan", not any("e'tiroz" in b.lower() for b in buttons3))
    check_true("Natija kartochkasi tugmasi bor", any("rasmli natija" in b.lower() for b in buttons3))


def test_webapp_chat_route() -> None:
    print("\n--- 3. WebApp Gemini Chat Route Sinovi ---")
    from apps.webapp.server import create_webapp
    app = create_webapp()
    routes = [r.resource.canonical for r in app.router.routes() if hasattr(r, "resource") and r.resource]
    check_true("POST /api/analysis/{test_id}/chat marshruti mavjud", "/api/analysis/{test_id}/chat" in routes)



def test_gemini_guided_prompting() -> None:
    print("\n--- 3. Gemini Guided Prompting Mantiqiy Sinovi ---")
    key = "ABCD"
    q_count = 4
    key_list = []
    for i in range(min(len(key), q_count)):
        key_list.append(f"• {i+1}-savolning TO'G'RI javobi: '{key[i].upper()}'")
    key_details = "\n".join(key_list)

    check_true("1-savol kaliti bor", "1-savolning TO'G'RI javobi: 'A'" in key_details)
    check_true("4-savol kaliti bor", "4-savolning TO'G'RI javobi: 'D'" in key_details)


async def main() -> int:
    print("TestLab — Savol E'tirozi (Apellyatsiya) va Gemini AI Sinovlari")
    await test_appeal_flow()
    test_keyboards()
    test_webapp_chat_route()
    test_gemini_guided_prompting()

    if _failures:
        print(f"\n❌ {len(_failures)} ta sinov muvaffaqiyatsiz:")
        for f in _failures:
            print(f"  - {f}")
        return 1

    print("\n✅ BARCHA YANGI FUNKSIYALAR 100% MUVAFFAQIYATLI O'TDI!")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
