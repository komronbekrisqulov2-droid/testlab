"""
Savollar tahlili: chalg'ituvchi variant va kalit xatosini sezish.

NEGA BU SINOV BOR
-----------------
`question_breakdown()` ilgari faqat «nechta to'g'ri / xato / javobsiz»
ni sanardi. Bu «savol qiyin» deyishga yetadi, lekin NEGA qiyinligini
aytmaydi.

Endi u xato javoblarning QAYSI harfga to'planganini ham hisoblaydi.
Bundan eng qimmatli xulosa chiqadi: agar deyarli hech kim «to'g'ri»
javobni topmagan bo'lsa-yu, xato qilganlar bir joyga to'plangan
bo'lsa — ehtimol savol emas, KALITNING O'ZI noto'g'ri.

Bu sinov chegaralarni tekshiradi: tasodifiy sochilgan xatolar
ogohlantirish chiqarmasligi, kam ishtirokchida esa umuman xulosa
qilinmasligi kerak.

Ishga tushirish:
    python tests/test_analysis.py
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

from apps.bot.texts import uz  # noqa: E402
from core.security.permissions import Role  # noqa: E402
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.assessment.service import AssessmentService  # noqa: E402
from modules.catalog.repository import CategoryRepository  # noqa: E402
from modules.catalog.service import CatalogService  # noqa: E402
from modules.identity.models import User  # noqa: E402
from modules.identity.repository import UserRepository  # noqa: E402
from modules.registry import Base  # noqa: E402

#  Telegram xabar chegarasi
MAX_MESSAGE_LENGTH = 4096

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


def check_true(label: str, condition: bool) -> None:
    check(label, bool(condition), True)


async def make_user(session, telegram_id: int, first: str, role: str) -> User:
    users = UserRepository(session)
    user, _ = await users.get_or_create(telegram_id, first_name=first, last_name="Sinov")
    user.role = role
    user.is_registered = True
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
        teacher = await make_user(session, 100, "Ustoz", Role.TEACHER.value)

        for index in range(1, 7):
            await make_user(session, 200 + index, f"O'quvchi{index}", Role.STUDENT.value)

        catalog = CatalogService(session)
        #  Kalit: a b c d
        await catalog.create_from_one_line(teacher, "Kalit shubhali+abcd")
        await catalog.create_from_one_line(teacher, "Kam ishtirokchi+abcd")

        await session.commit()
        print("  OK   1 o'qituvchi, 6 o'quvchi, 2 ta test")

    # ==================================================================
    print("\n--- 1. Javoblar yig'iladi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        users = UserRepository(session)
        test = await assessment.tests.get_by_number(1)

        #  1-savol (kalit «a»): 6 kishidan 5 tasi «c» deb belgilagan.
        #  Bunday to'planish tasodifiy emas — kalit shubhali.
        #  3-savol (kalit «c»): xatolar «a» va «d» ga sochilgan.
        answers = ("cbcd", "cbcd", "cbad", "cbad", "cbdd", "bbdd")

        for index, letters in enumerate(answers, start=1):
            student = await users.get_by_telegram_id(200 + index)
            await assessment.submit(test, student, letters)

        await session.commit()
        print("  OK   6 ta javob qabul qilindi")

    # ==================================================================
    print("\n--- 2. Chalg'ituvchi variant aniqlanadi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        test = await assessment.tests.get_by_number(1)

        rows = await assessment.question_breakdown(test)
        check("4 ta savol", len(rows), 4)

        first = rows[0]
        check("1-savolni hech kim topmadi", first["correct"], 0)
        check("ko'pchilik tanlagan xato", first["top_wrong"], "C")
        check("nechta tanlagan", first["top_wrong_count"], 5)

        second = rows[1]
        check("2-savolni hamma topdi", second["correct"], 6)
        check("xato bo'lmasa chalg'ituvchi yo'q", second["top_wrong"], "")

        await session.commit()

    # ==================================================================
    print("\n--- 3. Kalit shubhasi faqat to'plangan xatoda ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        test = await assessment.tests.get_by_number(1)
        rows = await assessment.question_breakdown(test)

        check("1-savol: kalit shubhali", rows[0]["suspect_key"], True)
        check("2-savol: hamma topgan", rows[1]["suspect_key"], False)

        #  3-savolda 2 kishi topgan, xatolar «a» va «d» ga teng bo'lingan —
        #  bu qiyin savol, lekin kalit xatosi emas
        check("3-savol: xatolar sochilgan", rows[2]["suspect_key"], False)
        check("3-savol baribir qiyin", rows[2]["note"], "Qiyin")

        await session.commit()

    # ==================================================================
    print("\n--- 4. Kam ishtirokchida xulosa chiqarilmaydi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        users = UserRepository(session)
        small = await assessment.tests.get_by_number(2)

        #  Aynan o'sha naqsh, lekin atigi 4 kishi: 4 tadan 4 tasi bir xil
        #  xato qilishi butunlay tasodif bo'lishi mumkin
        for index, letters in enumerate(("cbcd", "cbcd", "cbcd", "cbcd"), start=1):
            student = await users.get_by_telegram_id(200 + index)
            await assessment.submit(small, student, letters)

        rows = await assessment.question_breakdown(small)

        check("xato baribir sanaldi", rows[0]["top_wrong_count"], 4)
        check("lekin ogohlantirish yo'q", rows[0]["suspect_key"], False)

        await session.commit()

    # ==================================================================
    print("\n--- 5. O'qituvchiga ko'rsatiladigan matn ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        test = await assessment.tests.get_by_number(1)
        rows = await assessment.question_breakdown(test)

        text = uz.question_analysis(test, rows, participants=6, page=1)

        check_true("ogohlantirish bor", "KALITNI TEKSHIRING" in text)
        check_true("qaysi savol ekani aytilgan", "1-savol" in text)
        check_true("kalitdagi harf ko'rsatilgan", "<b>A</b>" in text)
        check_true("ko'pchilik tanlagani ko'rsatilgan", "<b>C</b>" in text)
        check_true("eng qiyinlari sanab o'tilgan", "Eng qiyinlari" in text)
        check_true("chegaraga sig'di", len(text) <= MAX_MESSAGE_LENGTH)

        #  Hech kim javob bermagan test — xato bermasligi kerak
        empty = uz.question_analysis(test, [], participants=0, page=1)
        check_true("bo'sh tahlil xato bermaydi", "ma'lumot yo'q" in empty)

        await session.commit()

    # ==================================================================
    print("\n--- 6. Katta test sahifalarga bo'linadi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        assessment = AssessmentService(session)
        users = UserRepository(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)

        #  60 savol — bitta xabarga sig'maydi
        key = "".join("abcd"[index % 4] for index in range(60))
        big = await catalog.create_from_one_line(teacher, f"Katta+{key}")

        student = await users.get_by_telegram_id(201)
        await assessment.submit(big, student, "d" * 60)

        rows = await assessment.question_breakdown(big)
        check("60 ta savol", len(rows), 60)
        check("3 sahifa", uz.analysis_pages(rows), 3)

        for page in (1, 2, 3):
            text = uz.question_analysis(big, rows, participants=1, page=page)
            check_true(f"{page}-sahifa chegaraga sig'di", len(text) <= MAX_MESSAGE_LENGTH)

        #  Chegaradan tashqaridagi sahifa oxirgisiga tenglashtiriladi —
        #  buzuq callback bilan bo'sh ekran chiqmasin
        edge = uz.question_analysis(big, rows, participants=1, page=99)
        check_true("chegaradan tashqari sahifa tuzatildi", "3/3" in edge)

        await session.commit()

    # ==================================================================
    print()
    if _failures:
        print(f"  {len(_failures)} TA SINOV YIQILDI:")
        for label in _failures:
            print(f"     • {label}")
        return 1

    print("  SAVOLLAR TAHLILI TO'G'RI")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
