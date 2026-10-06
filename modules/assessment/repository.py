"""Urinishlar repozitoriysi."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from core.datetime_utils import utcnow
from infrastructure.database.repository import BaseRepository, Page
from modules.assessment.models import Attempt, AttemptStatus

#  Yakunlangan deb hisoblanadigan holatlar
FINISHED_STATUSES = (
    AttemptStatus.FINISHED.value,
    AttemptStatus.EXPIRED.value,
    AttemptStatus.CANCELLED.value,
)


class AttemptRepository(BaseRepository[Attempt]):
    """Yechish urinishlari."""

    model = Attempt

    # ------------------------------------------------------------------
    #  O'qish
    # ------------------------------------------------------------------

    async def get_full(self, attempt_id: int) -> Attempt | None:
        """Urinishni test va foydalanuvchi bilan yuklaydi."""
        return await self.session.scalar(
            select(Attempt)
            .where(Attempt.id == attempt_id)
            .options(selectinload(Attempt.test), selectinload(Attempt.user))
        )

    async def get_active(self, user_id: int, test_id: int) -> Attempt | None:
        """Yakunlanmagan urinish (interaktiv rejim uchun)."""
        return await self.session.scalar(
            select(Attempt)
            .where(
                Attempt.user_id == user_id,
                Attempt.test_id == test_id,
                Attempt.status == AttemptStatus.IN_PROGRESS.value,
            )
            .limit(1)
        )

    async def list_overdue(self, *, limit: int = 200) -> list[Attempt]:
        """
        Muddati o'tgan, lekin hali yopilmagan urinishlar.

        Fon vazifasi shu ro'yxatni yopadi. `ix_attempts_status_deadline`
        indeksi aynan shu so'rov uchun qo'yilgan.

        `limit` — bir seansda yopiladigan maksimal son. Bot uzoq
        o'chib turgandan keyin minglab yozuv to'planishi mumkin; ularni
        bir tranzaksiyada yopish bazani ham, Telegram chegarasini ham
        urib yuboradi. Qolganlari keyingi yurishda yopiladi.
        """
        statement = (
            select(Attempt)
            .where(
                Attempt.status == AttemptStatus.IN_PROGRESS.value,
                Attempt.deadline.is_not(None),
                Attempt.deadline < utcnow(),
            )
            .options(selectinload(Attempt.user), selectinload(Attempt.test))
            .order_by(Attempt.deadline.asc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_by_user_and_test(
        self, user_id: int, test_id: int, *, official_only: bool = False
    ) -> int:
        """Foydalanuvchi bu testga necha marta javob bergan."""
        query = (
            select(func.count())
            .select_from(Attempt)
            .where(
                Attempt.user_id == user_id,
                Attempt.test_id == test_id,
                Attempt.status.in_(FINISHED_STATUSES),
            )
        )
        if official_only:
            query = query.where(or_(Attempt.is_practice == False, Attempt.is_practice.is_(None)))
        total = await self.session.scalar(query)
        return int(total or 0)

    async def get_first_completed(self, user_id: int, test_id: int) -> Attempt | None:
        """Foydalanuvchining 1-rasmiy urinishini qaytaradi."""
        statement = (
            select(Attempt)
            .where(
                Attempt.user_id == user_id,
                Attempt.test_id == test_id,
                Attempt.status.in_(FINISHED_STATUSES),
                or_(Attempt.is_practice == False, Attempt.is_practice.is_(None)),
            )
            .order_by(Attempt.id.asc())
        )
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def count_finished_by_test(self, test_id: int, *, official_only: bool = True) -> int:
        query = (
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.test_id == test_id, Attempt.status.in_(FINISHED_STATUSES))
        )
        if official_only:
            query = query.where(or_(Attempt.is_practice == False, Attempt.is_practice.is_(None)))
        total = await self.session.scalar(query)
        return int(total or 0)

    # ------------------------------------------------------------------
    #  Ro'yxatlar
    # ------------------------------------------------------------------

    def _by_test_statement(self, test_id: int, *, by_rank: bool, official_only: bool = True):
        statement = (
            select(Attempt)
            .where(Attempt.test_id == test_id, Attempt.status.in_(FINISHED_STATUSES))
            .options(selectinload(Attempt.user))
        )
        if official_only:
            statement = statement.where(or_(Attempt.is_practice == False, Attempt.is_practice.is_(None)))

        if by_rank:
            #  Teng foizda tezroq yechgan oldinda
            return statement.order_by(
                Attempt.percentage.desc(),
                Attempt.duration_sec.asc(),
                Attempt.finished_at.asc(),
            )

        return statement.order_by(Attempt.finished_at.desc())

    async def list_by_test(
        self,
        test_id: int,
        *,
        page: int = 1,
        per_page: int = 10,
        by_rank: bool = True,
        official_only: bool = True,
    ) -> Page[Attempt]:
        """
        Testni yechganlar ro'yxati.

        `by_rank=True` — reyting tartibida (medallar shunga tayanadi).
        `by_rank=False` — vaqt bo'yicha, oxirgisi birinchi (tarix).
        """
        return await self.paginate(
            self._by_test_statement(test_id, by_rank=by_rank, official_only=official_only),
            page=page,
            per_page=per_page,
        )

    async def list_all_by_test(self, test_id: int, *, official_only: bool = True) -> list[Attempt]:
        """Excel hisoboti uchun — sahifalashsiz, reyting tartibida."""
        result = await self.session.execute(
            self._by_test_statement(test_id, by_rank=True, official_only=official_only)
        )
        return list(result.scalars().all())

    async def list_by_user(
        self,
        user_id: int,
        *,
        page: int = 1,
        per_page: int = 8,
    ) -> Page[Attempt]:
        """Foydalanuvchining natijalari tarixi."""
        statement = (
            select(Attempt)
            .where(Attempt.user_id == user_id, Attempt.status.in_(FINISHED_STATUSES))
            .options(selectinload(Attempt.test))
            .order_by(Attempt.finished_at.desc())
        )
        return await self.paginate(statement, page=page, per_page=per_page)

    async def list_recent(
        self,
        *,
        page: int = 1,
        per_page: int = 10,
        since: datetime | None = None,
    ) -> Page[Attempt]:
        """
        Barcha yechganlar — admin paneli uchun.

        Filtr: davr bo'yicha.
        """
        statement = (
            select(Attempt)
            .where(Attempt.status.in_(FINISHED_STATUSES))
            .options(selectinload(Attempt.user), selectinload(Attempt.test))
        )
        if since is not None:
            statement = statement.where(Attempt.finished_at >= since)

        statement = statement.order_by(Attempt.finished_at.desc())
        return await self.paginate(statement, page=page, per_page=per_page)

    async def list_recent_for_export(self, since: datetime | None = None) -> list[Attempt]:
        """Admin Excel hisoboti uchun."""
        statement = (
            select(Attempt)
            .where(Attempt.status.in_(FINISHED_STATUSES))
            .options(selectinload(Attempt.user), selectinload(Attempt.test))
        )
        if since is not None:
            statement = statement.where(Attempt.finished_at >= since)

        result = await self.session.execute(statement.order_by(Attempt.finished_at.desc()))
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    #  Reyting
    # ------------------------------------------------------------------

    async def rank_in_test(self, attempt: Attempt) -> tuple[int, int]:
        """
        Urinishning test ichidagi o'rni.

        Returns:
            (o'rin, jami ishtirokchilar)
        """
        total = await self.count_finished_by_test(attempt.test_id, official_only=True)

        target = attempt
        if attempt.is_practice:
            first = await self.get_first_completed(attempt.user_id, attempt.test_id)
            if first is not None:
                target = first

        better = await self.session.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(
                Attempt.test_id == target.test_id,
                Attempt.status.in_(FINISHED_STATUSES),
                or_(Attempt.is_practice == False, Attempt.is_practice.is_(None)),
                Attempt.percentage > target.percentage,
            )
        )
        return int(better or 0) + 1, total

    async def leaderboard(self, test_id: int, limit: int = 10) -> list[Attempt]:
        """Test bo'yicha eng yaxshi natijalar."""
        result = await self.session.execute(
            self._by_test_statement(test_id, by_rank=True, official_only=True).limit(limit)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    #  Statistika
    # ------------------------------------------------------------------

    async def recent_percentages(self, user_id: int, limit: int = 6) -> list[float]:
        """
        Foydalanuvchining oxirgi natijalari — eng eskisidan yangisiga.

        Natija kartochkasidagi o'sish grafigi uchun. Tartib ataylab
        teskari: grafik chapdan o'ngga o'sishni ko'rsatishi kerak.
        """
        statement = (
            select(Attempt.percentage)
            .where(
                Attempt.user_id == user_id,
                Attempt.status.in_(FINISHED_STATUSES),
                or_(Attempt.is_practice == False, Attempt.is_practice.is_(None)),
            )
            .order_by(Attempt.finished_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        values = [float(row[0]) for row in result.all()]
        return list(reversed(values))

    async def user_stats(self, user_id: int) -> dict[str, float | int]:
        """Profil uchun."""
        base = (
            Attempt.user_id == user_id,
            Attempt.status.in_(FINISHED_STATUSES),
            or_(Attempt.is_practice == False, Attempt.is_practice.is_(None)),
        )

        total = await self.session.scalar(
            select(func.count()).select_from(Attempt).where(*base)
        )
        passed = await self.session.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(*base, Attempt.is_passed.is_(True))
        )
        average = await self.session.scalar(
            select(func.avg(Attempt.percentage)).where(*base)
        )
        best = await self.session.scalar(
            select(func.max(Attempt.percentage)).where(*base)
        )
        unique_tests = await self.session.scalar(
            select(func.count(func.distinct(Attempt.test_id))).where(*base)
        )

        return {
            "total": int(total or 0),
            "passed": int(passed or 0),
            "average": round(float(average or 0.0), 1),
            "best": round(float(best or 0.0), 1),
            "unique_tests": int(unique_tests or 0),
        }

    async def global_stats(self, since: datetime | None = None) -> dict[str, float | int]:
        """Admin dashboard uchun."""
        conditions = [Attempt.status.in_(FINISHED_STATUSES)]
        if since is not None:
            conditions.append(Attempt.finished_at >= since)

        total = await self.session.scalar(
            select(func.count()).select_from(Attempt).where(*conditions)
        )
        participants = await self.session.scalar(
            select(func.count(func.distinct(Attempt.user_id))).where(*conditions)
        )
        average = await self.session.scalar(
            select(func.avg(Attempt.percentage)).where(*conditions)
        )

        return {
            "total": int(total or 0),
            "participants": int(participants or 0),
            "average": round(float(average or 0.0), 1),
        }
