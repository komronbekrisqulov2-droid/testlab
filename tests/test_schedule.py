"""
Seriya (streak), vaqt chegarasi va jadval sinovi.

NEGA BU SINOV BOR
-----------------
Uchala funksiya ham bazada MAYDONI bor, lekin ularni yozadigan kod
yo'q edi:

  * `streak_days` natija kartochkasida chizilardi — doim 0 bo'lib.
  * `deadline` uchun indeks ham bor edi, lekin `begin()` hech qayerdan
    chaqirilmasdi (ichida `timedelta` hatto import ham qilinmagan edi).
  * `starts_at` / `ends_at` faqat yechishga urinilganda tekshirilardi,
    testning HOLATI esa o'zgarmasdi.

Bu sinov uchalasini ham uchidan-uchiga tekshiradi.

Ishga tushirish:
    python tests/test_schedule.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#  ⚠️ MUHIM: engine importidan OLDIN — sinov ALOHIDA bazani ishlatadi,
#  aks holda ishlaydigan botning ma'lumotlari o'chib ketadi.
from tests import _env  # noqa: F401,E402

from core.datetime_utils import utcnow  # noqa: E402
from core.exceptions import TestNotAvailableError  # noqa: E402
from core.security.permissions import Role  # noqa: E402
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.assessment.models import AttemptStatus  # noqa: E402
from modules.assessment.service import (  # noqa: E402
    XP_FINISHED,
    XP_PASSED_BONUS,
    XP_PER_CORRECT,
    XP_PERFECT_BONUS,
    XP_STREAK_BONUS,
    AssessmentService,
)
from modules.catalog.models import TestStatus  # noqa: E402
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


#  Har bir sinov testi «abcd» kaliti bilan 100% yechiladi — demak
#  bazaviy mukofot doim bir xil. Faqat SERIYA bonusi farq qiladi.
XP_PERFECT_RUN = (
    XP_FINISHED + 4 * XP_PER_CORRECT + XP_PASSED_BONUS + XP_PERFECT_BONUS
)


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
        await make_user(session, 200, "Doimiy", Role.STUDENT.value)
        await make_user(session, 300, "Shoshqaloq", Role.STUDENT.value)
        await make_user(session, 400, "Kechikkan", Role.STUDENT.value)

        catalog = CatalogService(session)
        for index in range(1, 5):
            await catalog.create_from_one_line(teacher, f"Seriya-{index}+abcd")

        await session.commit()
        print("  OK   1 o'qituvchi, 3 o'quvchi, 4 ta test")

    # ==================================================================
    print("\n--- 1. Seriya birinchi kunda boshlanadi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        student = await UserRepository(session).get_by_telegram_id(200)
        test = await assessment.tests.get_by_number(1)

        result = await assessment.submit(test, student, "abcd")

        check("seriya 1 dan boshlandi", result.streak, 1)
        check("seriya o'sdi deb belgilandi", result.streak_grew, True)
        check("bazaga yozildi", student.streak_days, 1)
        check("sana belgilandi", student.streak_updated_on is not None, True)

        #  Birinchi kun bonussiz — «seriya» so'zi ma'nosini yo'qotmasin
        check("birinchi kunda bonus yo'q", result.xp_earned, XP_PERFECT_RUN)
        await session.commit()

    # ==================================================================
    print("\n--- 2. Bir kunda ikkinchi test seriyani oshirmaydi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        student = await UserRepository(session).get_by_telegram_id(200)
        test = await assessment.tests.get_by_number(2)

        result = await assessment.submit(test, student, "abcd")

        check("seriya o'zgarmadi", result.streak, 1)
        check("o'smadi deb belgilandi", result.streak_grew, False)
        check("takroriy bonus berilmadi", result.xp_earned, XP_PERFECT_RUN)
        await session.commit()

    # ==================================================================
    print("\n--- 3. Kecha yechgan bo'lsa seriya o'sadi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        student = await UserRepository(session).get_by_telegram_id(200)

        #  Kechagi holatni taqlid qilamiz
        student.streak_updated_on = utcnow() - timedelta(days=1)
        student.streak_days = 4
        await session.flush()

        test = await assessment.tests.get_by_number(3)
        result = await assessment.submit(test, student, "abcd")

        check("seriya o'sdi", result.streak, 5)
        check("bazada ham o'sdi", student.streak_days, 5)
        check("seriya bonusi berildi", result.xp_earned, XP_PERFECT_RUN + XP_STREAK_BONUS)
        await session.commit()

    # ==================================================================
    print("\n--- 4. Uzilgan seriya 1 dan qayta boshlanadi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        student = await UserRepository(session).get_by_telegram_id(200)

        student.streak_updated_on = utcnow() - timedelta(days=5)
        student.streak_days = 12
        await session.flush()

        test = await assessment.tests.get_by_number(4)
        result = await assessment.submit(test, student, "abcd")

        check("seriya tiklandi", result.streak, 1)
        check("tiklangan seriyaga bonus yo'q", result.xp_earned, XP_PERFECT_RUN)
        await session.commit()

    # ==================================================================
    print("\n--- 5. Vaqt chegarasi: urinish ochiladi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        assessment = AssessmentService(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)
        student = await UserRepository(session).get_by_telegram_id(300)

        timed = await catalog.create_from_one_line(teacher, "Vaqtli+abcd")
        await catalog.update_settings(timed, teacher, time_limit_min=10)

        attempt = await assessment.begin(timed, student)

        check("urinish yaratildi", attempt is not None, True)
        check("holat: jarayonda", attempt.status, AttemptStatus.IN_PROGRESS.value)
        check("muddat qo'yildi", attempt.deadline is not None, True)
        check("maksimal ball kalitdan", attempt.max_score, 4)

        #  Tugmani ikki marta bosish vaqtni qaytadan boshlamasligi kerak
        again = await assessment.begin(timed, student)
        check("ikkinchi chaqiruv o'shani qaytardi", again.id, attempt.id)

        await session.commit()

    # ==================================================================
    print("\n--- 6. Javob O'SHA urinishga yoziladi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        student = await UserRepository(session).get_by_telegram_id(300)
        timed = await assessment.tests.get_by_number(5)

        result = await assessment.submit(timed, student, "abcd")

        rows = await assessment.attempts.list_by(user_id=student.id, test_id=timed.id)
        check("dublikat qator yaratilmadi", len(rows), 1)
        check("holat yakunlandi", result.attempt.status, AttemptStatus.FINISHED.value)
        check("natija to'g'ri", result.percentage, 100.0)
        check("davomiylik o'lchandi", result.attempt.duration_sec >= 0, True)

        await session.commit()

    # ==================================================================
    print("\n--- 7. Vaqt tugagach javob qabul qilinmaydi ---")
    async with session_factory() as session:
        assessment = AssessmentService(session)
        student = await UserRepository(session).get_by_telegram_id(400)
        timed = await assessment.tests.get_by_number(5)

        attempt = await assessment.begin(timed, student)
        attempt.deadline = utcnow() - timedelta(seconds=1)
        await session.flush()

        await expect_error(
            "kechikkan javob rad etildi",
            assessment.submit(timed, student, "abcd"),
            TestNotAvailableError,
        )

        check("urinish yopildi", attempt.status, AttemptStatus.EXPIRED.value)
        check("natija nol", attempt.percentage, 0.0)
        await session.commit()

    # ==================================================================
    print("\n--- 8. Fon vazifasi muddati o'tganlarni yopadi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        assessment = AssessmentService(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)
        student = await UserRepository(session).get_by_telegram_id(300)

        abandoned = await catalog.create_from_one_line(teacher, "Tashlandiq+abcdab")
        await catalog.update_settings(abandoned, teacher, time_limit_min=5)

        attempt = await assessment.begin(abandoned, student)
        attempt.deadline = utcnow() - timedelta(minutes=1)
        await session.flush()

        expired = await assessment.expire_overdue()

        check("bitta urinish yopildi", len(expired), 1)
        check("holat: muddati o'tgan", attempt.status, AttemptStatus.EXPIRED.value)
        check("javobsizlar sanaldi", attempt.skipped_count, 6)
        check("yakun vaqti muddatga tenglashtirildi", attempt.finished_at, attempt.deadline)
        check("keshlangan statistika yangilandi", abandoned.attempts_count, 1)

        #  Ikkinchi yurish bo'sh qaytishi kerak — aks holda fon vazifasi
        #  har daqiqada bir xil xabarni qayta yuborardi
        check("takroriy yurish bo'sh", await assessment.expire_overdue(), [])

        await session.commit()

    # ==================================================================
    print("\n--- 9. Jadval: vaqti kelgan test o'zi ochiladi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)

        due = await catalog.create_draft(teacher, title="Vaqti keldi")
        await catalog.set_answer_key(due, teacher, "abcd")
        due.starts_at = utcnow() - timedelta(minutes=1)

        later = await catalog.create_draft(teacher, title="Hali erta")
        await catalog.set_answer_key(later, teacher, "abcd")
        later.starts_at = utcnow() + timedelta(days=1)

        keyless = await catalog.create_draft(teacher, title="Kalitsiz")
        keyless.starts_at = utcnow() - timedelta(minutes=1)

        await session.flush()

        opened = await catalog.open_scheduled()

        check("bitta test ochildi", [test.id for test in opened], [due.id])
        check("holat e'lon qilingan", due.status, TestStatus.PUBLISHED.value)
        check("e'lon vaqti yozildi", due.published_at is not None, True)
        check("kelajakdagi test tegilmadi", later.status, TestStatus.DRAFT.value)
        check("kalitsiz test ochilmadi", keyless.status, TestStatus.DRAFT.value)

        await session.commit()

    # ==================================================================
    print("\n--- 10. Jadval: muddati tugagan test arxivlanadi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        teacher = await UserRepository(session).get_by_telegram_id(100)

        finished = await catalog.create_from_one_line(teacher, "Tugadi+abcd")
        finished.ends_at = utcnow() - timedelta(minutes=1)

        endless = await catalog.create_from_one_line(teacher, "Muddatsiz+abcd")

        await session.flush()

        closed = await catalog.close_expired()

        check("bitta test yopildi", [test.id for test in closed], [finished.id])
        check("arxivga o'tdi", finished.status, TestStatus.ARCHIVED.value)
        check("muddatsiz test tegilmadi", endless.status, TestStatus.PUBLISHED.value)
        check("takroriy yurish bo'sh", await catalog.close_expired(), [])

        await session.commit()

    # ==================================================================
    print()
    if _failures:
        print(f"  {len(_failures)} TA SINOV YIQILDI:")
        for label in _failures:
            print(f"     • {label}")
        return 1

    print("  SERIYA, VAQT CHEGARASI VA JADVAL TO'G'RI")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
