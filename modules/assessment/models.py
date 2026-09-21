"""
Yechish urinishi.

Bitta urinish = bitta yuborilgan javoblar qatori (`submitted_key`).
Har bir savol uchun alohida yozuv saqlanmaydi: natija `submitted_key`
va `answer_key` ni solishtirish orqali istalgan paytda hisoblanadi.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.datetime_utils import utcnow
from infrastructure.database.base import Base, BigIntPK

if TYPE_CHECKING:
    from modules.catalog.models import Test
    from modules.identity.models import User


class AttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    EXPIRED = "expired"       # vaqt tugadi
    CANCELLED = "cancelled"


#  Baho shkalasi: (minimal foiz, belgi, nomi, emoji)
GRADE_SCALE: tuple[tuple[int, str, str, str], ...] = (
    (90, "A+", "A'lo", "🏆"),
    (80, "A", "Juda yaxshi", "🥇"),
    (70, "B", "Yaxshi", "🥈"),
    (60, "C", "Qoniqarli", "🥉"),
    (40, "D", "Qoniqarsiz", "📉"),
    (0, "F", "Yiqildi", "❌"),
)


def grade_for(percentage: float) -> tuple[str, str, str]:
    """Foiz bo'yicha baho: (belgi, nomi, emoji)."""
    for minimum, symbol, name, emoji in GRADE_SCALE:
        if percentage >= minimum:
            return symbol, name, emoji
    return "F", "Yiqildi", "❌"


class Attempt(Base, BigIntPK):
    """
    Bitta yechish urinishi.

    MUHIM: holat FSM'da emas, BAZADA saqlanadi. Bot qayta ishga tushsa
    ham o'quvchi yarim yechgan testini yo'qotmaydi.
    """

    __tablename__ = "attempts"
    __table_args__ = (
        Index("ix_attempts_test_user", "test_id", "user_id"),
        Index("ix_attempts_user_status", "user_id", "status"),
        Index("ix_attempts_test_percentage", "test_id", "percentage"),
        Index("ix_attempts_status_deadline", "status", "deadline"),
        {"comment": "Yechish urinishlari"},
    )

    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default=AttemptStatus.IN_PROGRESS.value,
        server_default=AttemptStatus.IN_PROGRESS.value,
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------
    #  Javoblar
    # ------------------------------------------------------------------
    submitted_key: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        doc="Yuborilgan javoblar. Javobsiz savol o'rnida '-'",
    )

    # ------------------------------------------------------------------
    #  Vaqt
    # ------------------------------------------------------------------
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True, doc="None = cheksiz"
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_sec: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # ------------------------------------------------------------------
    #  Natija
    # ------------------------------------------------------------------
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_score: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    percentage: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0", nullable=False, index=True
    )
    grade: Mapped[str | None] = mapped_column(String(4), nullable=True)
    is_passed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    correct_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    wrong_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # ------------------------------------------------------------------
    #  Bog'lanishlar
    # ------------------------------------------------------------------
    test: Mapped["Test"] = relationship(back_populates="attempts", lazy="selectin")
    user: Mapped["User"] = relationship(back_populates="attempts", lazy="selectin")

    # ------------------------------------------------------------------
    #  Xossalar
    # ------------------------------------------------------------------

    @property
    def is_finished(self) -> bool:
        return self.status in (AttemptStatus.FINISHED.value, AttemptStatus.EXPIRED.value)

    @property
    def is_active(self) -> bool:
        return self.status == AttemptStatus.IN_PROGRESS.value

    @property
    def is_expired(self) -> bool:
        """Muddat o'tganmi?"""
        return self.deadline is not None and utcnow() > self.deadline

    @property
    def seconds_left(self) -> int | None:
        """Qolgan vaqt (soniya). Cheksiz bo'lsa None."""
        if self.deadline is None:
            return None
        return max(0, int((self.deadline - utcnow()).total_seconds()))

    @property
    def grade_meta(self) -> tuple[str, str, str]:
        return grade_for(self.percentage)


class StudentMistake(Base, BigIntPK):
    """
    O'quvchining xatolar daftari.

    Har bir xato qilingan savol saqlanadi. O'quvchi xatolar ustida ishlaganda
    (retake) to'g'ri topshirsa, `is_resolved=True` bo'ladi.
    """

    __tablename__ = "student_mistakes"
    __table_args__ = (
        Index("ix_student_mistakes_user_resolved", "user_id", "is_resolved"),
        Index("ix_student_mistakes_test_qnum", "test_id", "question_number"),
        {"comment": "O'quvchi xatolari daftari"},
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    given_answer: Mapped[str] = mapped_column(String(8), nullable=False)
    correct_answer: Mapped[str] = mapped_column(String(8), nullable=False)
    is_resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    test: Mapped["Test"] = relationship(lazy="selectin")
    user: Mapped["User"] = relationship(lazy="selectin")

