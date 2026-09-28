"""
Sinf va guruhlar (Classroom) modellari.

O'qituvchi o'z o'quvchilarini guruhlarga (masalan: "10-A sinf", "Matematika repetitor")
ajratishi, maxsus havola orqali a'zo qilishi, yopiq testlar e'lon qilishi va
guruh reytingini ko'rishi mumkin.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.datetime_utils import utcnow
from infrastructure.database.base import (
    Base,
    BigIntPK,
    IntPK,
    TimestampMixin,
)

if TYPE_CHECKING:
    from modules.catalog.models import Test
    from modules.identity.models import User


class Classroom(Base, IntPK, TimestampMixin):
    """
    O'qituvchi sinfi / o'quv guruhi.
    """

    __tablename__ = "classrooms"
    __table_args__ = (
        Index("ix_classrooms_teacher_active", "teacher_id", "is_active"),
        {"comment": "Sinf va o'quv guruhlari"},
    )

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        nullable=False,
        index=True,
        doc="Guruhga qo'shilish kodi (masalan: 7K9M2P)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )

    # --- Bog'lanishlar ---
    teacher: Mapped["User"] = relationship(
        foreign_keys=[teacher_id], lazy="selectin"
    )
    members: Mapped[list["ClassroomMember"]] = relationship(
        back_populates="classroom",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    tests: Mapped[list["Test"]] = relationship(
        back_populates="classroom",
        lazy="selectin",
    )

    @property
    def members_count(self) -> int:
        return len(self.members) if self.members else 0

    @property
    def tests_count(self) -> int:
        return len(self.tests) if self.tests else 0


class ClassroomMember(Base, BigIntPK):
    """
    Sinf / guruh a'zosi (o'quvchi).
    """

    __tablename__ = "classroom_members"
    __table_args__ = (
        UniqueConstraint("classroom_id", "user_id", name="uq_classroom_member"),
        Index("ix_classroom_members_class_user", "classroom_id", "user_id"),
        {"comment": "Guruh / Sinf a'zolari"},
    )

    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    # --- Bog'lanishlar ---
    classroom: Mapped["Classroom"] = relationship(
        back_populates="members", lazy="selectin"
    )
    user: Mapped["User"] = relationship(lazy="selectin")

