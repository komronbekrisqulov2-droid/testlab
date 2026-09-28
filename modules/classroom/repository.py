"""
Sinf va guruhlar (Classroom) repozitoriysi.
"""

from __future__ import annotations

import secrets
import string
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.datetime_utils import utcnow
from core.logging import get_logger
from modules.assessment.models import Attempt, AttemptStatus
from modules.catalog.models import Test
from modules.classroom.models import Classroom, ClassroomMember

log = get_logger(__name__)


def _generate_code(length: int = 6) -> str:
    """O'quvchilar qo'shilishi uchun takrorlanmas qisqa kod."""
    alphabet = string.ascii_uppercase + string.digits
    # Adashish mumkin bo'lgan belgilarni (0, O, 1, I) chiqaramiz
    for char in ("0", "O", "1", "I"):
        alphabet = alphabet.replace(char, "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


class ClassroomRepository:
    """Sinf va guruhlar bazasi bilan ishlash."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        teacher_id: int,
        name: str,
        description: str | None = None,
    ) -> Classroom:
        """Yangi guruh yaratadi."""
        # Unikal kod hosil qilamiz
        code = _generate_code(6)
        while await self.get_by_code(code) is not None:
            code = _generate_code(6)

        classroom = Classroom(
            teacher_id=teacher_id,
            name=name.strip(),
            description=description.strip() if description else None,
            code=code,
            is_active=True,
        )
        self.session.add(classroom)
        await self.session.flush()
        log.info("🏫 Yangi guruh yaratildi: %s (kod: %s, o'qituvchi: %d)", name, code, teacher_id)
        return classroom

    async def get(self, classroom_id: int) -> Classroom | None:
        """ID bo'yicha guruhni oladi."""
        stmt = select(Classroom).where(Classroom.id == classroom_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Classroom | None:
        """Kod bo'yicha guruhni topadi."""
        clean_code = code.strip().upper()
        stmt = select(Classroom).where(func.upper(Classroom.code) == clean_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_teacher(self, teacher_id: int) -> list[Classroom]:
        """O'qituvchining barcha guruhlari."""
        stmt = (
            select(Classroom)
            .where(Classroom.teacher_id == teacher_id, Classroom.is_active.is_(True))
            .order_by(Classroom.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_student(self, user_id: int) -> list[Classroom]:
        """O'quvchi a'zo bo'lgan barcha guruhlar."""
        stmt = (
            select(Classroom)
            .join(ClassroomMember, ClassroomMember.classroom_id == Classroom.id)
            .where(ClassroomMember.user_id == user_id, Classroom.is_active.is_(True))
            .order_by(ClassroomMember.joined_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def is_member(self, classroom_id: int, user_id: int) -> bool:
        """O'quvchi ushbu guruhga a'zomi?"""
        stmt = select(ClassroomMember.id).where(
            ClassroomMember.classroom_id == classroom_id,
            ClassroomMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def add_member(self, classroom_id: int, user_id: int) -> ClassroomMember | None:
        """O'quvchini guruhga a'zo qiladi (agar hali bo'lmasa)."""
        if await self.is_member(classroom_id, user_id):
            return None

        member = ClassroomMember(
            classroom_id=classroom_id,
            user_id=user_id,
            joined_at=utcnow(),
        )
        self.session.add(member)
        await self.session.flush()
        log.info("👤 O'quvchi guruhga qo'shildi: user_id=%d, classroom_id=%d", user_id, classroom_id)
        return member

    async def remove_member(self, classroom_id: int, user_id: int) -> bool:
        """O'quvchini guruhdan chiqaradi."""
        stmt = delete(ClassroomMember).where(
            ClassroomMember.classroom_id == classroom_id,
            ClassroomMember.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        return (res.rowcount or 0) > 0

    async def get_members(self, classroom_id: int) -> list[ClassroomMember]:
        """Guruhning barcha a'zolari."""
        stmt = (
            select(ClassroomMember)
            .where(ClassroomMember.classroom_id == classroom_id)
            .order_by(ClassroomMember.joined_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_members(self, classroom_id: int) -> int:
        """Guruh a'zolari soni."""
        stmt = select(func.count(ClassroomMember.id)).where(
            ClassroomMember.classroom_id == classroom_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def delete(self, classroom: Classroom) -> None:
        """Guruhni o'chiradi."""
        await self.session.delete(classroom)
        await self.session.flush()

    async def get_leaderboard(self, classroom_id: int) -> list[dict[str, Any]]:
        """
        Sinf o'quvchilarining umumiy reytingi.

        Guruh testlari bo'yicha har bir o'quvchining yechgan testlari soni,
        o'rtacha balli va eng yaxshi natijasi hisoblanadi.
        """
        members = await self.get_members(classroom_id)
        if not members:
            return []

        # Guruhga biriktirilgan test ID'lari
        test_ids_stmt = select(Test.id).where(Test.classroom_id == classroom_id)
        res_test_ids = await self.session.execute(test_ids_stmt)
        class_test_ids = set(res_test_ids.scalars().all())

        leaderboard = []
        for m in members:
            user = m.user
            # Agar sinfga xos testlar bo'lsa faqat ularni, aks holda hamma urinishlarni olamiz
            att_stmt = select(Attempt).where(
                Attempt.user_id == user.id,
                Attempt.status == AttemptStatus.FINISHED.value,
            )
            if class_test_ids:
                att_stmt = att_stmt.where(Attempt.test_id.in_(class_test_ids))

            res_att = await self.session.execute(att_stmt)
            attempts = list(res_att.scalars().all())

            if attempts:
                avg_pct = round(sum(a.percentage for a in attempts) / len(attempts), 1)
                best_pct = max(a.percentage for a in attempts)
                count = len(attempts)
            else:
                avg_pct = 0.0
                best_pct = 0.0
                count = 0

            leaderboard.append({
                "user": user,
                "tests_count": count,
                "avg_percentage": avg_pct,
                "best_percentage": best_pct,
            })

        # Reyting bo'yicha saralash: o'rtacha foiz desc, yechilgan testlar soni desc
        leaderboard.sort(key=lambda x: (x["avg_percentage"], x["tests_count"]), reverse=True)
        return leaderboard
