"""
Smart UX & Interaktivlik imkoniyatlari sinovi:
1. Xatolar ustida ishlash (Personal Retake & Mistakes Notebook)
2. Savollar tushuntirishi (Explanations)
3. Ota-ona / Repetitorga hisobot (Parent Linking & Notification)
4. WebApp API va ma'lumotlar uzatish

Ishga tushirish:
    python tests/test_smart_ux.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ⚠️ MUHIM: engine importidan OLDIN sinov bazasi
from tests import _env  # noqa: F401,E402

from core.security.permissions import Role  # noqa: E402
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.assessment.service import AssessmentService  # noqa: E402
from modules.catalog.service import CatalogService  # noqa: E402
from modules.identity.models import User  # noqa: E402
from modules.identity.repository import UserRepository  # noqa: E402
from modules.registry import Base  # noqa: E402
from apps.bot.texts import uz  # noqa: E402

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


async def make_user(session, telegram_id: int, first: str, last: str, role: str) -> User:
    users = UserRepository(session)
    user, _ = await users.get_or_create(telegram_id, first_name=first, last_name=last)
    user.role = role
    user.is_registered = True
    await session.flush()
    return user


async def main() -> int:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    print("\n--- 1. Tayyorgarlik ---")
    async with session_factory() as session:
        teacher = await make_user(session, 100, "O'qituvchi", "Ustoz", Role.TEACHER.value)
        student = await make_user(session, 200, "Ali", "Valiyev", Role.STUDENT.value)
        parent = await make_user(session, 300, "Vali", "Ota", Role.STUDENT.value)
        await session.commit()
        print("  OK   Foydalanuvchilar yaratildi")

    # ==================================================================
    print("\n--- 2. Test yaratish va Xatolar ustida ishlash (Personal Retake) ---")
    test_id: int = 0
    async with session_factory() as session:
        catalog = CatalogService(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)
        # 5 ta savolli test: to'g'ri javoblar abcde
        test = await catalog.create_from_one_line(teacher, "Fizika-1+abcde")
        test_id = test.id
        check("Test yaratildi", test.questions_count, 5)

        # O'quvchi javob beradi: abcaa (4-savol: d o'rniga a; 5-savol: e o'rniga a)
        assessment = AssessmentService(session)
        student = await UserRepository(session).get_by_telegram_id(200)
        result = await assessment.submit(test, student, "abcaa")
        check("To'g'ri javoblar soni", result.correct, 3)

        # Xatolarni tekshirish: 2 ta xato saqlangan bo'lishi kerak (savol 4 va 5)
        mistakes = await assessment.get_mistakes(student.id, test_id=test_id)
        check("Xatolar soni", len(mistakes), 2)
        sorted_m = sorted(mistakes, key=lambda m: m.question_number)
        check("1-xato savol raqami", sorted_m[0].question_number, 4)
        check("1-xato kiritilgan javob", sorted_m[0].given_answer, "A")
        check("1-xato to'g'ri javob", sorted_m[0].correct_answer, "D")
        check("2-xato savol raqami", sorted_m[1].question_number, 5)

        # Barcha xatolarni hisoblash
        total_mistakes = await assessment.count_mistakes(student.id)
        check("Jami xatolar soni", total_mistakes, 2)

        # Bitta xatoni to'g'irlash (Personal retake)
        mistake_to_resolve = sorted_m[0]
        resolved = await assessment.resolve_mistake(student.id, mistake_to_resolve.id)
        check("Xato to'g'irlandi", resolved, True)

        # Qolgan xatolar 1 ta bo'lishi kerak
        active_mistakes = await assessment.get_mistakes(student.id)
        check("Faol xatolar soni", len(active_mistakes), 1)
        check("Qolgan xato savol raqami", active_mistakes[0].question_number, 5)

        # Xatolarni tozalash (Clear)
        cleared_count = await assessment.clear_mistakes(student.id)
        check("Tozalangan xatolar", cleared_count, 1)
        check("Tozalangandan keyingi xatolar", await assessment.count_mistakes(student.id), 0)

        await session.commit()

    # ==================================================================
    print("\n--- 3. Savollarning tushuntirishi (Explanations) ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        # O'qituvchi 1 va 4-savollarga tushuntirish qo'shadi
        test = await catalog.tests.get(test_id)
        teacher = await UserRepository(session).get_by_telegram_id(100)
        exp1 = await catalog.set_explanation(
            test=test,
            user=teacher,
            question_number=1,
            text="1-savol formulasi: v = s / t. Tezlik formulasi orqali topiladi.",
        )
        check("1-savol tushuntirish qo'shildi", exp1.question_number, 1)

        exp4 = await catalog.set_explanation(
            test=test,
            user=teacher,
            question_number=4,
            text="4-savol yechimi: Nyutonning 2-qonuni F = ma.",
        )
        check("4-savol tushuntirish qo'shildi", exp4.question_number, 4)

        # Tushuntirishni yangilash
        exp1_updated = await catalog.set_explanation(
            test=test,
            user=teacher,
            question_number=1,
            text="1-savol yangilangan yechimi: v = s / t (tezlik).",
        )
        check("1-savol tushuntirish yangilandi", exp1_updated.explanation_text, "1-savol yangilangan yechimi: v = s / t (tezlik).")

        # Tushuntirishlar ro'yxatini olish
        explanations = await catalog.get_explanations(test_id=test_id)
        check("Tushuntirishlar soni", len(explanations), 2)
        check("Tushuntirishlar savol raqamlari", sorted(explanations.keys()), [1, 4])

        await session.commit()

    # ==================================================================
    print("\n--- 4. Ota-ona / Repetitor bog'lanishi (Parent Linking & Reporting) ---")
    async with session_factory() as session:
        users = UserRepository(session)
        student = await users.get_by_telegram_id(200)
        parent = await users.get_by_telegram_id(300)

        # Ota-onani ulash
        link = await users.link_parent(
            student_id=student.id,
            parent_telegram_id=parent.telegram_id,
            parent_name=parent.full_name,
            relationship_type="parent",
        )
        check("Ota-ona ulandi", link.parent_telegram_id, 300)

        # Ulanganlarni tekshirish
        parents = await users.get_parent_links(student.id)
        check("Ulangan nazoratchilar soni", len(parents), 1)
        check("Ulangan ota-ona ismi", parents[0].parent_name, "Vali Ota")

        # Ota-ona uchun xabarnoma matnini tekshirish
        msg = uz.parent_notification(result, student)
        check("Xabarnomada o'quvchi ismi bor", student.full_name in msg, True)
        check("Xabarnomada test nomi bor", test.title in msg, True)
        check("Xabarnomada ball ko'rsatilgan", "3/5" in msg, True)

        # Ota-onani uzish
        unlinked = await users.unlink_parent(student.id, link.id)
        check("Ota-ona hisobdan uzildi", unlinked, True)
        check("Uzilgandan so'ng ulanganlar soni", len(await users.get_parent_links(student.id)), 0)

        await session.commit()

    # ==================================================================
    print("\n--- 5. WebApp API Serveri sinovi ---")
    from apps.webapp.server import create_webapp_app
    from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop, TestClient, TestServer
    from aiohttp import web

    app = create_webapp_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # 1. Mavjud test haqida ma'lumot olish API (/api/test/{id})
        resp = await client.get(f"/api/test/{test_id}")
        check("API status", resp.status, 200)
        data = await resp.json()
        check("API test mavzusi", data.get("title"), "Fizika-1")
        check("API savollar soni", data.get("questions_count"), 5)

        # 2. Mavjud bo'lmagan test
        resp_404 = await client.get("/api/test/999999")
        check("API 404 status", resp_404.status, 404)

        # 3. WebApp HTML sahifasi (/test/{id})
        resp_html = await client.get(f"/test/{test_id}")
        check("HTML sahifa status", resp_html.status, 200)
        html_text = await resp_html.text()
        check("HTML ichida WebApp mavjud", "TestLab — Interaktiv Test Yechish" in html_text, True)
    finally:
        await client.close()

    # ==================================================================
    print("\n" + "=" * 50)
    if _failures:
        print(f"❌ YIQILDI: {len(_failures)} ta sinov o'tmadi:")
        for fail in _failures:
            print(f"   - {fail}")
        return 1

    print("✅ BARCHA SMART UX SINOVLARI MUVAFFAQIYATLI O'TDI!")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
