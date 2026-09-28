"""
Randomizatsiya va Sinf/Guruh boshqaruvi sinovlari.

Tekshiradi:
    1. Randomizatsiya:
       * test.is_randomized = True bo'lganda savollar tartibi har bir o'quvchi uchun aralashishi
       * random_questions_count berilganda aynan shuncha savol tanlanishi
       * javoblar aynan o'quvchiga tushgan random tartib bo'yicha baholanishi
       * xatolar daftari asl savol raqamini to'g'ri eslab qolishi
    2. Guruh/Sinf:
       * o'qituvchi guruh yaratishi va unikal kod olishi
       * o'quvchi guruhga a'zo bo'lishi
       * testni guruhga biriktirish
       * guruh a'zosi testni yecha olishi, begona o'quvchi kira olmasligi
       * sinf reytingi (leaderboard) to'g'ri hisoblanishi
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401,E402

from core.exceptions import TestNotAvailableError
from core.security.permissions import Role
from infrastructure.database.engine import engine, session_factory
from modules.assessment.service import AssessmentService
from modules.catalog.service import CatalogService
from modules.classroom.repository import ClassroomRepository
from modules.identity.models import User
from modules.identity.repository import UserRepository
from modules.registry import Base

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


def check_true(label: str, value: bool) -> None:
    check(label, bool(value), True)


async def run_tests() -> None:
    # 0. Bazani tozalab qayta yaratamiz
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user_repo = UserRepository(session)
        teacher, _ = await user_repo.get_or_create(111111, first_name="Ustoz", last_name="Karimov")
        teacher.role = Role.TEACHER.value
        teacher.is_registered = True

        student1, _ = await user_repo.get_or_create(222222, first_name="Ali", last_name="Valiyev")
        student1.role = Role.STUDENT.value
        student1.is_registered = True

        student2, _ = await user_repo.get_or_create(333333, first_name="Vali", last_name="Aliyev")
        student2.role = Role.STUDENT.value
        student2.is_registered = True

        outsider, _ = await user_repo.get_or_create(444444, first_name="Begona", last_name="O'quvchi")
        outsider.role = Role.STUDENT.value
        outsider.is_registered = True

        await session.commit()

    print("\n--- 1. RANDOMIZATSIYA (Savollar banki va aralashtirish) ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        assessment = AssessmentService(session)

        teacher = await UserRepository(session).get_by_telegram_id(111111)
        student1 = await UserRepository(session).get_by_telegram_id(222222)
        student2 = await UserRepository(session).get_by_telegram_id(333333)
        outsider = await UserRepository(session).get_by_telegram_id(444444)

        # 10 ta savolli test yaratamiz: abcdeabcde
        original_key = "abcdeabcde"
        test = await catalog.create_from_one_line(teacher, f"Biologiya 10-sinf+{original_key}")
        test.is_randomized = True
        test.random_questions_count = 5  # 10 tadan 5 tasi tushsin
        await session.commit()

        check_true("test.is_randomized yoqildi", test.is_randomized)
        check("test.random_questions_count", test.random_questions_count, 5)

        # 1-o'quvchi testni boshlaydi
        attempt1 = await assessment.begin(test, student1)
        check_true("attempt1 yaratildi", attempt1 is not None)
        check_true("attempt1.question_order mavjud", bool(attempt1.question_order))
        check_true("attempt1.effective_key mavjud", bool(attempt1.effective_key))

        order1 = [int(x) for x in attempt1.question_order.split(",")]
        check("attempt1 savollar soni 5 ta", len(order1), 5)
        check("effective_key uzunligi 5 ta", len(attempt1.effective_key), 5)

        # Har bir savol original_key ga to'g'ri mos kelganini tekshiramiz
        expected_key1 = "".join(original_key[i - 1] for i in order1)
        check("effective_key original_key bilan mos", attempt1.effective_key, expected_key1)

        # 2-o'quvchi testni boshlaydi
        attempt2 = await assessment.begin(test, student2)
        order2 = [int(x) for x in attempt2.question_order.split(",")]
        check("attempt2 savollar soni 5 ta", len(order2), 5)

        # O'quvchi 1 to'g'ri javoblarni yuboradi
        sub1 = await assessment.submit(test, student1, attempt1.effective_key)
        check("student1 100% natija oldi", sub1.percentage, 100.0)
        check("student1 5 ta to'g'ri", sub1.correct, 5)

        # Savollarning haqiqiy original_number lari tekshiriladi
        check("sub1 savol 1 original_number", sub1.questions[0].original_number, order1[0])
        check("sub1 savol 5 original_number", sub1.questions[4].original_number, order1[4])

        # O'quvchi 2 esa bitta to'g'ri, qolganini noto'g'ri yuboradi
        c0 = attempt2.effective_key[0]
        diff_letters = "".join("b" if c == "a" else "a" for c in attempt2.effective_key[1:])
        wrong_answers = c0 + diff_letters
        sub2 = await assessment.submit(test, student2, wrong_answers)
        check("student2 1 ta to'g'ri", sub2.correct, 1)
        check("student2 4 ta xato", sub2.wrong, 4)

        # 3. Savollar tahlili (question_breakdown) random uchun to'g'ri ishlashini tekshirish
        breakdown = await assessment.question_breakdown(test)
        check("breakdown barcha 10 ta savol uchun", len(breakdown), 10)
        for row in breakdown:
            check_true(f"savol #{row['number']} foiz hisoblangan", row["rate"] >= 0.0)

        # 4. Kalit yangilanganda qayta hisoblash (recalculate_all)
        recalculated = await assessment.recalculate_all(test)
        check_true("recalculate_all muvaffaqiyatli ishladi", isinstance(recalculated, list))

        # 5. UI matnlari (uz.py) randomizatsiya uchun to'g'ri shakllanishini tekshirish
        from apps.bot.texts import uz
        card_t = uz.test_card(test, 2, attempt=attempt1)
        check_true("test_card da RANDOM tartibi ko'rsatilgan", "RANDOM REJIM" in card_t)
        check_true(f"test_card da #{order1[0]} bor", f"#{order1[0]}" in card_t)

        ask_t = uz.ask_answers(test, attempt=attempt1)
        check_true("ask_answers da 5 ta savol", "5 ta" in ask_t)
        check_true(f"ask_answers da #{order1[0]} ko'rsatilgan", f"#{order1[0]}" in ask_t)

        res_t = uz.result(sub1)
        check_true("result matnida 5 ta savol", "5 ta" in res_t)

        detail_t = uz.attempt_detail_text(attempt1)
        check_true("attempt_detail_text da Asl savol raqami bor", "Asl #" in detail_t)

    print("\n--- 2. SINF VA GURUHLAR (CLASSROOM) ---")
    async with session_factory() as session:
        cls_repo = ClassroomRepository(session)
        catalog = CatalogService(session)
        assessment = AssessmentService(session)
        teacher = await UserRepository(session).get_by_telegram_id(111111)
        student1 = await UserRepository(session).get_by_telegram_id(222222)
        student2 = await UserRepository(session).get_by_telegram_id(333333)
        outsider = await UserRepository(session).get_by_telegram_id(444444)

        # O'qituvchi guruh yaratadi
        cls = await cls_repo.create(
            teacher_id=teacher.id,
            name="10-A Matematika",
            description="10-A sinf o'quvchilari uchun maxsus guruh",
        )
        await session.commit()

        check("guruh nomi", cls.name, "10-A Matematika")
        check_true("guruh kodi mavjud", bool(cls.code) and len(cls.code) == 6)

        # student1 va student2 guruhga a'zo bo'ladi
        m1 = await cls_repo.add_member(cls.id, student1.id)
        m2 = await cls_repo.add_member(cls.id, student2.id)
        await session.commit()

        check_true("student1 a'zo bo'ldi", m1 is not None)
        check_true("student2 a'zo bo'ldi", m2 is not None)
        check_true("student1 guruhda bor", await cls_repo.is_member(cls.id, student1.id))
        check_true("outsider guruhda yo'q", not await cls_repo.is_member(cls.id, outsider.id))

        # Yopiq test yaratamiz va guruhga biriktiramiz
        group_test = await catalog.create_from_one_line(
            teacher,
            "10-A Matematika Nazorat+abcdabcd",
        )
        group_test.classroom_id = cls.id
        await session.commit()

        check("test guruhga biriktirildi", group_test.classroom_id, cls.id)

        # Guruh a'zosi testni yechishi mumkin
        try:
            await assessment.ensure_can_answer(group_test, student1)
            print("  OK   guruh a'zosi testga kira oldi")
        except Exception as e:
            print(f"  FAIL guruh a'zosi kira olmadi: {e}")
            _failures.append("guruh a'zosi kira olmadi")

        # Begona o'quvchi yopiq testga KIRA OLMAYDI
        outsider_blocked = False
        try:
            await assessment.ensure_can_answer(group_test, outsider)
        except TestNotAvailableError:
            outsider_blocked = True
        except Exception:
            pass

        check_true("begona o'quvchi yopiq testdan to'sildi", outsider_blocked)

        # student1 va student2 guruh testini yechadi
        await assessment.submit(group_test, student1, "abcdabcd")
        await assessment.submit(group_test, student2, "abcdaaaa")

        # Sinf reytingi (leaderboard)
        board = await cls_repo.get_leaderboard(cls.id)
        check("sinf reytingida 2 ta o'quvchi", len(board), 2)
        # O'quvchining o'z guruhlari ro'yxati (student perspective)
        student1_classes = await cls_repo.list_by_student(student1.id)
        check("student1 a'zo bo'lgan guruhlar soni 1 ta", len(student1_classes), 1)
        check("student1 guruh nomi", student1_classes[0].name, "10-A Matematika")

        # student2 guruhdan chiqadi (leave group)
        left = await cls_repo.remove_member(cls.id, student2.id)
        check_true("student2 guruhdan chiqdi", left)
        check_true("student2 endi guruhda yo'q", not await cls_repo.is_member(cls.id, student2.id))
        check("student2 chiqqach guruhda 1 ta o'quvchi qoldi", await cls_repo.count_members(cls.id), 1)

    if _failures:
        print(f"\n❌ {len(_failures)} TA SINOV YIQILDI:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n🎉 BARCHA RANDOMIZATSIYA VA SINF SINOVLARI MUVAFFAQIYATLI O'TDI!\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
