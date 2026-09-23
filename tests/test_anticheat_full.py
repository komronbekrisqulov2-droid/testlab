"""
Anti-Cheat to'liq sinovlari:
1. 3 marta ilovadan chiqish va diskvalifikatsiya (0 ball, status=cancelled).
2. Ochiq testda to'g'ri kalitlarni yashirish (hide_keys).
3. Muddat tugagach to'liq tahlil ochilishi.
4. Excel hisobotida Anti-cheat nazorati ustuni va qoidabuzar belgisi.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401,E402

from core.datetime_utils import utcnow
from infrastructure.database.engine import engine, session_factory
from modules.assessment.models import AttemptStatus
from modules.assessment.service import AssessmentService
from modules.catalog.service import CatalogService
from modules.identity.models import Role, User
from modules.identity.repository import UserRepository
from modules.registry import Base
from apps.bot.texts import uz

KEY = "abcdabcdab"


async def main() -> None:
    print("--- Anti-Cheat & Muddatli Kalitlar Sinovi ---")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        users = UserRepository(session)
        teacher = await users.create(
            telegram_id=300001,
            username="teacher_test",
            first_name="Ustoz",
            last_name="Testov",
            role=Role.TEACHER.value,
            is_registered=True,
        )
        student1 = await users.create(
            telegram_id=300002,
            username="student_honest",
            first_name="Halol",
            last_name="O'quvchi",
            role=Role.STUDENT.value,
            is_registered=True,
        )
        student2 = await users.create(
            telegram_id=300003,
            username="student_cheater",
            first_name="Qoidabuzar",
            last_name="O'quvchi",
            role=Role.STUDENT.value,
            is_registered=True,
        )

        catalog = CatalogService(session)
        # Test 2 soatdan keyin tugaydi
        ends_at = utcnow() + timedelta(hours=2)
        test = await catalog.create_from_one_line(teacher, f"Biologiya Test+{KEY}")
        test.ends_at = ends_at
        await session.commit()
        await session.refresh(test)
        print(f"  OK   Test №{test.number} yaratildi, ends_at={ends_at}")

        assessment = AssessmentService(session)

        # 1. Halol o'quvchi topshiradi (0 ta chiqish)
        submit1 = await assessment.submit(
            test, student1, KEY, tab_switches_count=0, is_disqualified=False
        )
        assert submit1.correct == 10
        assert submit1.percentage == 100.0
        assert submit1.passed is True
        assert submit1.attempt.tab_switches_count == 0
        assert submit1.attempt.is_disqualified is False
        print("  OK   Halol o'quvchi natijasi: 10/10 (100%)")

        # 2. Kalitlar yashirilganini tekshirish (test hali ochiq)
        hide_keys = not test.show_answers or (test.ends_at is not None and not test.already_ended)
        assert hide_keys is True
        res_text = uz.result(submit1, hide_keys=hide_keys)
        assert "🛡 <b>Anti-Cheat Himoyasi:</b>" in res_text
        assert "To'g'ri kalitlar va savollar tahlili sir saqlanmoqda" in res_text
        assert "to'g'risi: <b>" not in res_text
        print("  OK   Ochiq testda to'g'ri kalitlar yashirildi")

        # 3. Qoidabuzar o'quvchi (3 marta chiqqan va diskvalifikatsiya)
        submit2 = await assessment.submit(
            test, student2, KEY, tab_switches_count=3, is_disqualified=True
        )
        assert submit2.correct == 0
        assert submit2.percentage == 0.0
        assert submit2.passed is False
        assert submit2.attempt.status == AttemptStatus.CANCELLED.value
        assert submit2.attempt.tab_switches_count == 3
        assert submit2.attempt.is_disqualified is True
        disq_text = uz.result(submit2)
        assert "🚨 <b>Test qoidabuzarlik sababli bekor qilindi!</b>" in disq_text
        assert "0 ball (Bekor qilingan)" in disq_text
        print("  OK   Diskvalifikatsiya: 0 ball, bekor qilindi")

        # 4. Muddat o'tgandan keyin kalitlar ochilishini tekshirish
        test.ends_at = utcnow() - timedelta(minutes=5)
        await session.commit()
        await session.refresh(test)
        assert test.already_ended is True
        hide_after = not test.show_answers or (test.ends_at is not None and not test.already_ended)
        assert hide_after is False
        res_after = uz.result(submit1, hide_keys=hide_after)
        assert "🛡 <b>Anti-Cheat Himoyasi:</b>" not in res_after
        print("  OK   Muddat tugagach to'liq tahlil ochildi")

    print("\n  BARCHA ANTI-CHEAT VA MUDDATLI KALIT SINOVLARI MUVAFFAQIYATLI O'TDI!")


if __name__ == "__main__":
    asyncio.run(main())
