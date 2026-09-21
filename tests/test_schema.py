"""
Sxema sinovi.

Tekshiradi:
    * barcha kutilgan jadvallar reyestrda bormi
    * jadvallar haqiqatan yaratiladimi
    * kaskad o'chirish ishlaydimi (SQLite'da PRAGMA yoqilganmi)
    * RBAC meros zanjiri to'g'rimi

Ishga tushirish:
    python tests/test_schema.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#  ⚠️ MUHIM: engine importidan OLDIN — sinov ALOHIDA bazani ishlatadi,
#  aks holda ishlaydigan botning ma'lumotlari o'chib ketadi.
from tests import _env  # noqa: F401,E402

from sqlalchemy import func, select, text  # noqa: E402

from core.security.permissions import (  # noqa: E402
    Permission,
    Role,
    has_permission,
)
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.assessment.models import Attempt, AttemptStatus, grade_for  # noqa: E402
from modules.catalog.models import Category, Test, TestMedia  # noqa: E402
from modules.identity.models import User  # noqa: E402
from modules.registry import EXPECTED_TABLES, Base  # noqa: E402

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


def check_true(label: str, value: bool) -> None:
    check(label, bool(value), True)


# ======================================================================
#  1. REYESTR
# ======================================================================

def test_registry() -> None:
    print("\n--- Reyestr ---")
    actual = set(Base.metadata.tables)

    check("jadvallar soni", len(actual), len(EXPECTED_TABLES))

    missing = EXPECTED_TABLES - actual
    check("tushib qolgan jadval yo'q", missing, set())

    extra = actual - EXPECTED_TABLES
    check("ortiqcha jadval yo'q", extra, set())


def test_constraints_named() -> None:
    """
    Har bir cheklov nomlangan bo'lishi kerak.

    Nomsiz cheklovni SQLite'da o'zgartirib bo'lmaydi — Alembic
    migratsiyasi ishlamay qoladi.
    """
    print("\n--- Cheklov nomlari ---")
    unnamed: list[str] = []

    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if constraint.name is None:
                unnamed.append(f"{table.name}.{type(constraint).__name__}")
        for index in table.indexes:
            if index.name is None:
                unnamed.append(f"{table.name}.Index")

    check("nomsiz cheklov yo'q", unnamed, [])


# ======================================================================
#  2. RBAC
# ======================================================================

def test_rbac_inheritance() -> None:
    print("\n--- RBAC meros zanjiri ---")

    check_true("mehmon test yecha olmaydi",
               not has_permission(Role.GUEST, Permission.TEST_SOLVE))
    check_true("o'quvchi test yecha oladi",
               has_permission(Role.STUDENT, Permission.TEST_SOLVE))
    check_true("o'quvchi test yarata olmaydi",
               not has_permission(Role.STUDENT, Permission.TEST_CREATE))
    check_true("o'qituvchi test yarata oladi",
               has_permission(Role.TEACHER, Permission.TEST_CREATE))
    check_true("o'qituvchi test yecha ham oladi (meros)",
               has_permission(Role.TEACHER, Permission.TEST_SOLVE))
    check_true("o'qituvchi admin panelga kira olmaydi",
               not has_permission(Role.TEACHER, Permission.ADMIN_PANEL))
    check_true("admin panelga kiradi",
               has_permission(Role.ADMIN, Permission.ADMIN_PANEL))
    check_true("admin test ham yarata oladi (meros)",
               has_permission(Role.ADMIN, Permission.TEST_CREATE))
    check_true("faqat super admin o'chira oladi",
               has_permission(Role.SUPER_ADMIN, Permission.USERS_DELETE)
               and not has_permission(Role.ADMIN, Permission.USERS_DELETE))
    check_true("noma'lum rol eng past huquq oladi",
               not has_permission("hacker", Permission.ADMIN_PANEL))


def test_banned_user_has_no_rights() -> None:
    print("\n--- Bloklangan foydalanuvchi ---")
    user = User(telegram_id=1, role=Role.ADMIN.value, is_banned=True)
    check_true("bloklangan admin panelga kira olmaydi",
               not user.can(Permission.ADMIN_PANEL))
    check_true("bloklangan test yecha olmaydi",
               not user.can(Permission.TEST_SOLVE))


# ======================================================================
#  3. BAHO
# ======================================================================

def test_grades() -> None:
    print("\n--- Baho shkalasi ---")
    check("100% -> A+", grade_for(100)[0], "A+")
    check("92%  -> A+", grade_for(92)[0], "A+")
    check("85%  -> A", grade_for(85)[0], "A")
    check("74%  -> B", grade_for(74)[0], "B")
    check("60%  -> C", grade_for(60)[0], "C")
    check("41%  -> D", grade_for(41)[0], "D")
    check("0%   -> F", grade_for(0)[0], "F")


# ======================================================================
#  4. BAZA
# ======================================================================

async def test_database() -> None:
    print("\n--- Baza ---")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    #  SQLite'da tashqi kalitlar yoqilganmi
    async with engine.connect() as connection:
        pragma = await connection.execute(text("PRAGMA foreign_keys"))
        check("PRAGMA foreign_keys yoqilgan", pragma.scalar(), 1)

    async with session_factory() as session:
        #  --- Ma'lumot yaratamiz ---
        teacher = User(
            telegram_id=100, first_name="Komronbek", last_name="Risqulov",
            role=Role.TEACHER.value, is_registered=True,
        )
        student = User(
            telegram_id=200, first_name="Komronbek", last_name="Risqulov",
            role=Role.STUDENT.value, is_registered=True,
        )
        category = Category(name="Matematika", emoji="🔢")
        session.add_all([teacher, student, category])
        await session.flush()

        test = Test(
            number=1, code="ABC123", title="Blok-3",
            author_id=teacher.id, category_id=category.id,
            answer_key="abcdabcdab",
            questions_count=10,
        )
        session.add(test)
        await session.flush()

        session.add_all([
            TestMedia(test_id=test.id, order_index=1, file_id="f1", file_unique_id="u1"),
            TestMedia(test_id=test.id, order_index=2, file_id="f2", file_unique_id="u2"),
        ])

        attempt = Attempt(
            test_id=test.id, user_id=student.id,
            status=AttemptStatus.FINISHED.value,
            submitted_key="abcdabcdad",
            score=9, max_score=10, percentage=90.0,
            grade="A+", is_passed=True,
            correct_count=9, wrong_count=1,
        )
        session.add(attempt)
        await session.commit()

        check("foydalanuvchilar", await session.scalar(select(func.count()).select_from(User)), 2)
        check("testlar", await session.scalar(select(func.count()).select_from(Test)), 1)
        check("rasmlar", await session.scalar(select(func.count()).select_from(TestMedia)), 2)
        check("urinishlar", await session.scalar(select(func.count()).select_from(Attempt)), 1)
        test_id = test.id
        student_id = student.id

    # ------------------------------------------------------------------
    #  Model xossalari — YANGI sessiyada.
    #
    #  Ataylab yangi sessiya: `session.get()` obyektni identity-map dan
    #  qaytaradi, ya'ni yuqorida `Test(...)` bilan yaratilgan O'SHA
    #  obyektni. Uning bog'lanishlari hech qachon yuklanmagan va
    #  `lazy="selectin"` ishlamaydi. Haqiqiy so'rovda esa test bazadan
    #  SELECT bilan olinadi — shuni takrorlaymiz.
    # ------------------------------------------------------------------
    print("\n--- Model xossalari (toza sessiya) ---")
    async with session_factory() as session:
        loaded = await session.scalar(select(Test).where(Test.id == test_id))

        check("public kod", loaded.number, 1)
        check("kalit harflari", loaded.key_letters, "abcdabcdab")
        check("muallif ismi", loaded.author_name, "Komronbek Risqulov")
        check("kategoriya", loaded.category_label, "🔢 Matematika")
        check("rasmlar soni", loaded.media_count, 2)
        check("qoralama -> yopiq", loaded.is_open, False)
        check("yopiq sababi", loaded.closed_reason(), "Bu test hali e'lon qilinmagan.")

        student_loaded = await session.scalar(select(User).where(User.id == student_id))
        check("to'liq ism", student_loaded.full_name, "Komronbek Risqulov")
        check("qisqa ism", student_loaded.short_name, "Komronbek R.")

    # ------------------------------------------------------------------
    #  Yuklanmagan bog'lanish xatoga OLIB KELMASLIGI kerak
    # ------------------------------------------------------------------
    print("\n--- Yuklanmagan bog'lanish himoyasi ---")
    fresh = Test(number=999, code="ZZZ999", title="Yangi", answer_key="abc")
    check("author_name xato bermaydi", fresh.author_name, "—")
    check("category_label xato bermaydi", fresh.category_label, "📦 Kategoriyasiz")
    check("media_count xato bermaydi", fresh.media_count, 0)

    #  --- Kaskad o'chirish ---
    async with session_factory() as session:
        test_row = await session.scalar(select(Test).limit(1))
        await session.delete(test_row)
        await session.commit()

    async with session_factory() as session:
        check("test o'chdi", await session.scalar(select(func.count()).select_from(Test)), 0)
        check("rasmlar kaskad o'chdi",
              await session.scalar(select(func.count()).select_from(TestMedia)), 0)
        check("urinishlar kaskad o'chdi",
              await session.scalar(select(func.count()).select_from(Attempt)), 0)
        check("foydalanuvchilar saqlanib qoldi",
              await session.scalar(select(func.count()).select_from(User)), 2)

    #  Tozalash
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ======================================================================

def main() -> int:
    print("\n  TestLab — sxema sinovlari")

    test_registry()
    test_constraints_named()
    test_rbac_inheritance()
    test_banned_user_has_no_rights()
    test_grades()
    asyncio.run(test_database())

    print()
    if _failures:
        print(f"  {len(_failures)} ta sinov muvaffaqiyatsiz:")
        for name in _failures:
            print(f"    - {name}")
        return 1

    print("  BARCHA SINOVLAR O'TDI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
