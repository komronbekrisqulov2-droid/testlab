"""
To'liq oqim sinovi: test yaratish -> javob berish -> natija -> tahlil.

Botsiz, to'g'ridan-to'g'ri servislar bilan ishlaydi.

Ishga tushirish:
    python tests/test_flow.py
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

from core.exceptions import (  # noqa: E402
    AlreadyAnsweredError,
    AnswerKeyError,
    ConflictError,
    PermissionDeniedError,
    TestNotAvailableError,
    TestNotFoundError,
)
from core.security.permissions import Role  # noqa: E402
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.assessment.service import AssessmentService  # noqa: E402
from modules.catalog.repository import CategoryRepository  # noqa: E402
from modules.catalog.service import CatalogService  # noqa: E402
from modules.identity.models import User  # noqa: E402
from modules.identity.repository import UserRepository  # noqa: E402
from modules.registry import Base  # noqa: E402

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


async def expect_error(label: str, coro, error) -> None:
    try:
        await coro
    except error:
        print(f"  OK   {label}")
    except Exception as unexpected:
        print(f"  FAIL {label}\n         kutilgan: {error.__name__}"
              f"\n         olingan : {type(unexpected).__name__}: {unexpected}")
        _failures.append(label)
    else:
        print(f"  FAIL {label} — xato kutilgan edi")
        _failures.append(label)


async def make_user(session, telegram_id, first, last, role, phone=None) -> User:
    users = UserRepository(session)
    user, _ = await users.get_or_create(telegram_id, first_name=first, last_name=last)
    user.role = role
    user.is_registered = True
    user.phone = phone
    await session.flush()
    return user


async def main() -> int:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    # ==================================================================
    print("\n--- Tayyorgarlik ---")
    async with session_factory() as session:
        await CategoryRepository(session).seed_defaults()
        await make_user(session, 100, "Saxobiddin", "Karimov", Role.TEACHER.value)
        await make_user(session, 200, "Komronbek", "Risqulov", Role.STUDENT.value, "+998901112233")
        await make_user(session, 300, "Aziz", "Karimov", Role.STUDENT.value, "+998901112244")
        await make_user(session, 400, "Malika", "Ergasheva", Role.STUDENT.value)
        await session.commit()
        print("  OK   4 foydalanuvchi, 13 kategoriya")

    # ==================================================================
    print("\n--- 1. Bitta xabarda test yaratish ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)

        test = await catalog.create_from_one_line(teacher, "Blok-3 Matematika+abcdabcdab")

        check("nom", test.title, "Blok-3 Matematika")
        check("kalit", test.answer_key, "abcdabcdab")
        check("savollar soni kalitdan", test.questions_count, 10)
        check("darhol e'lon qilindi", test.is_published, True)
        check("yechish mumkin", test.is_open, True)
        check("raqamli kod", test.number, 1)
        check("muallif yuklangan", test.author_name, "Saxobiddin Karimov")
        check("XP berildi", teacher.xp, 25)

        await session.commit()

    # ==================================================================
    print("\n--- 2. O'quvchi test yarata olmaydi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        student = await UserRepository(session).get_by_telegram_id(200)
        await expect_error(
            "huquq tekshirildi",
            catalog.create_from_one_line(student, "Test+abcd"),
            PermissionDeniedError,
        )

    # ==================================================================
    print("\n--- 3. Rasmli test (qoralama -> rasm -> kalit -> e'lon) ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)

        draft = await catalog.create_draft(teacher)
        check("avtomatik nom", draft.title, f"Test №{draft.number}")
        check("qoralama", draft.is_draft, True)

        problems = await catalog.readiness_problems(draft)
        check("kalit yo'qligi aniqlandi", problems, ["Javoblar kaliti kiritilmagan"])

        await expect_error(
            "kalitsiz e'lon qilib bo'lmaydi",
            catalog.publish(draft, teacher),
            ConflictError,
        )

        await catalog.add_media(draft, teacher, file_id="f1", file_unique_id="u1")
        await catalog.add_media(draft, teacher, file_id="f2", file_unique_id="u2")
        duplicate = await catalog.add_media(draft, teacher, file_id="x", file_unique_id="u1")
        check("dublikat rad etildi", duplicate, None)
        check("2 ta rasm", await catalog.media_count(draft), 2)

        await catalog.set_answer_key(draft, teacher, "1a2b3c4d5a")
        check("kalit raqamli formatdan", draft.answer_key, "abcda")
        check("savollar soni", draft.questions_count, 5)

        await catalog.publish(draft, teacher)
        check("e'lon qilindi", draft.is_published, True)

        await session.commit()
        photo_test_number = draft.number

    # ==================================================================
    print("\n--- 4. Testni kod bo'yicha topish ---")
    async with session_factory() as session:
        catalog = CatalogService(session)

        found = await catalog.find_for_solving("1")
        check("raqam bo'yicha", found.title, "Blok-3 Matematika")

        by_code = await catalog.find_for_solving(found.code)
        check("harfli kod bo'yicha", by_code.id, found.id)

        await expect_error(
            "yo'q test",
            catalog.find_for_solving("9999"),
            TestNotFoundError,
        )

    # ==================================================================
    print("\n--- 5. Javob berish ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        test = await CatalogService(session).find_for_solving("1")
        student = await UserRepository(session).get_by_telegram_id(200)

        #  Kalit "abcdabcdab", o'quvchi 9-savolda adashdi (a o'rniga d)
        result = await assessment.submit(test, student, "abcdabcddb")

        check("to'g'ri", result.correct, 9)
        check("xato", result.wrong, 1)
        check("javobsiz", result.skipped, 0)
        check("foiz", result.percentage, 90.0)
        check("baho", result.grade, "A+")
        check("o'tdi", result.passed, True)
        check("o'rin", result.rank, 1)
        check("savol natijalari", len(result.questions), 10)
        check("9-savol xato", result.questions[8].verdict, False)
        check("9-savolda bergani", result.questions[8].given, "D")
        check("9-savolning to'g'risi", result.questions[8].correct, "A")
        check("1-savol to'g'ri", result.questions[0].verdict, True)
        check("XP", result.xp_earned, 5 + 9 * 2 + 15)

        await session.commit()

    # ==================================================================
    print("\n--- 6. Takroriy javob taqiqlanadi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        test = await CatalogService(session).find_for_solving("1")
        student = await UserRepository(session).get_by_telegram_id(200)

        await expect_error(
            "bir marta qoidasi",
            assessment.submit(test, student, "abcdabcdab"),
            AlreadyAnsweredError,
        )

    # ==================================================================
    print("\n--- 7. Xato javoblar rad etiladi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        test = await CatalogService(session).find_for_solving("1")
        aziz = await UserRepository(session).get_by_telegram_id(300)

        await expect_error("qisqa javob", assessment.submit(test, aziz, "abc"), AnswerKeyError)
        await expect_error("noto'g'ri harf", assessment.submit(test, aziz, "abcdabcdxb"), AnswerKeyError)
        await expect_error("bo'sh", assessment.submit(test, aziz, "   "), AnswerKeyError)

        from core.exceptions import ValidationError
        await expect_error(
            "boshqa test raqami",
            assessment.submit(test, aziz, "99*abcdabcdab"),
            ValidationError,
        )

    # ==================================================================
    print("\n--- 8. Yana ikki o'quvchi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        catalog = CatalogService(session)
        test = await catalog.find_for_solving("1")

        aziz = await UserRepository(session).get_by_telegram_id(300)
        #  Test raqami bilan yuborish: "1*abcd..." (bu testning raqami 1)
        perfect = await assessment.submit(test, aziz, f"{test.number}*abcdabcdab")
        check("test raqami bilan yuborish", perfect.percentage, 100.0)
        check("perfect bonus", perfect.xp_earned, 5 + 10 * 2 + 15 + 50)

        malika = await UserRepository(session).get_by_telegram_id(400)
        weak = await assessment.submit(test, malika, "abcd------")
        check("javobsizlar", weak.skipped, 6)
        check("foiz", weak.percentage, 40.0)
        check("o'tmadi", weak.passed, False)

        await session.commit()

    # ==================================================================
    print("\n--- 9. Reyting va statistika ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        catalog = CatalogService(session)
        test = await catalog.tests.get_by_number(1)

        page = await assessment.attempts.list_by_test(test.id, by_rank=True)
        check("3 ta ishtirokchi", page.total, 3)

        order = [round(a.percentage) for a in page.items]
        check("reyting tartibi", order, [100, 90, 40])
        check("1-o'rin", page.items[0].user.full_name, "Aziz Karimov")

        await catalog.tests.refresh_stats(test)
        check("keshlangan urinishlar", test.attempts_count, 3)
        check("o'rtacha ball", test.avg_score, 76.7)

        stats = await assessment.attempts.user_stats(
            (await UserRepository(session).get_by_telegram_id(300)).id
        )
        check("Azizning testlari", stats["total"], 1)
        check("Azizning eng yaxshisi", stats["best"], 100.0)

    # ==================================================================
    print("\n--- 10. Savollar tahlili (qaysi savol qiyin) ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        test = await CatalogService(session).tests.get_by_number(1)

        rows = await assessment.question_breakdown(test)
        check("10 ta savol", len(rows), 10)
        check("1-savol raqami", rows[0]["number"], 1)
        check("1-savolning to'g'ri javobi", rows[0]["correct_letter"], "A")

        #  1-savol: uchalasi ham "a" yozgan -> 3 ta to'g'ri
        check("1-savolni hammasi topdi", rows[0]["correct"], 3)
        check("1-savol izohi", rows[0]["note"], "Juda oson")

        #  9-savol: Komronbek "d" (xato), Aziz "a" (to'g'ri), Malika "-" (javobsiz)
        check("9-savol to'g'ri", rows[8]["correct"], 1)
        check("9-savol xato", rows[8]["wrong"], 1)
        check("9-savol javobsiz", rows[8]["skipped"], 1)
        check("9-savol izohi", rows[8]["note"], "Qiyin")

    # ==================================================================
    print("\n--- 11. Arxivlangan testga javob berib bo'lmaydi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        assessment = AssessmentService(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)
        test = await catalog.tests.get_by_number(photo_test_number)

        await catalog.archive(test, teacher)
        await session.flush()

        student = await UserRepository(session).get_by_telegram_id(200)
        await expect_error(
            "arxiv yopiq",
            assessment.submit(test, student, "abcda"),
            TestNotAvailableError,
        )

    # ==================================================================
    print("\n--- 12. Begona testni tahrirlab bo'lmaydi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        student = await UserRepository(session).get_by_telegram_id(200)
        test = await catalog.tests.get_by_number(1)

        await expect_error(
            "egalik tekshirildi",
            catalog.set_answer_key(test, student, "aaaa"),
            PermissionDeniedError,
        )

    # ==================================================================
    await engine.dispose()

    print()
    if _failures:
        print(f"  {len(_failures)} ta sinov muvaffaqiyatsiz:")
        for name in _failures:
            print(f"    - {name}")
        return 1

    print("  TO'LIQ OQIM ISHLADI")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
