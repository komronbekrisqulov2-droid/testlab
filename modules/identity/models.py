"""Foydalanuvchi modeli."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


from core.datetime_utils import utcnow
from core.security.permissions import Permission, Role, has_permission, role_label
from infrastructure.database.base import (
    Base,
    BigIntPK,
    SoftDeleteMixin,
    TimestampMixin,
)

if TYPE_CHECKING:
    from modules.assessment.models import Attempt
    from modules.catalog.models import Test


class User(Base, BigIntPK, TimestampMixin, SoftDeleteMixin):
    """
    Bot foydalanuvchisi.

    `telegram_id` — Telegram bergan o'zgarmas raqam. Bizning `id` dan
    farq qiladi: ichki bog'lanishlarda `id`, Telegram bilan ishlashda
    `telegram_id` ishlatiladi.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_role_banned", "role", "is_banned"),
        Index("ix_users_xp_desc", "xp"),
        {"comment": "Foydalanuvchilar"},
    )

    # ------------------------------------------------------------------
    #  Telegram ma'lumotlari
    # ------------------------------------------------------------------
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
        doc="Telegram foydalanuvchi ID'si",
    )
    username: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, doc="@username (o'zgarishi mumkin)"
    )

    # ------------------------------------------------------------------
    #  Profil
    # ------------------------------------------------------------------
    first_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone: Mapped[str | None] = mapped_column(
        String(24), nullable=True, index=True, doc="Telefon raqam"
    )
    language: Mapped[str] = mapped_column(
        String(8), default="uz", server_default="uz", nullable=False
    )
    is_registered: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
        index=True,
        doc="Ro'yxatdan o'tish yakunlanganmi",
    )

    # ------------------------------------------------------------------
    #  Rol va kirish
    # ------------------------------------------------------------------
    role: Mapped[str] = mapped_column(
        String(16),
        default=Role.STUDENT.value,
        server_default=Role.STUDENT.value,
        nullable=False,
        index=True,
        doc="student / teacher / moderator / admin / super",
    )
    is_banned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False, index=True
    )
    ban_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ------------------------------------------------------------------
    #  Gamifikatsiya
    # ------------------------------------------------------------------
    xp: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False, doc="Tajriba ballari"
    )
    streak_days: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False, doc="Ketma-ket faol kunlar"
    )
    streak_updated_on: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, doc="Seriya oxirgi marta yangilangan kun"
    )

    # ------------------------------------------------------------------
    #  Sozlamalar
    # ------------------------------------------------------------------
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    show_in_leaderboard: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )

    # ------------------------------------------------------------------
    #  Faollik
    # ------------------------------------------------------------------
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True, doc="Oxirgi murojaat vaqti"
    )

    # ------------------------------------------------------------------
    #  Bog'lanishlar
    # ------------------------------------------------------------------
    tests: Mapped[list["Test"]] = relationship(
        back_populates="author",
        foreign_keys="Test.author_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    parent_links: Mapped[list["ParentStudentLink"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


    # ------------------------------------------------------------------
    #  Xossalar
    # ------------------------------------------------------------------

    @property
    def full_name(self) -> str:
        """Ism-familiya. Bo'lmasa username yoki ID."""
        parts = [part for part in (self.first_name, self.last_name) if part]
        if parts:
            return " ".join(parts)
        if self.username:
            return f"@{self.username}"
        return f"ID {self.telegram_id}"

    @property
    def short_name(self) -> str:
        """'Komronbek R.' — ro'yxatlarda joy tejash uchun."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name[0]}."
        return self.full_name

    @property
    def mention(self) -> str:
        """Telegram HTML havolasi."""
        return f'<a href="tg://user?id={self.telegram_id}">{self.full_name}</a>'

    @property
    def role_title(self) -> str:
        return role_label(self.role)

    def can(self, permission: Permission) -> bool:
        """
        Bu amalni bajara oladimi?

        Bloklangan foydalanuvchi hech narsa qila olmaydi — tekshiruv
        shu yerda markazlashtirilgan, har bir handler'da takrorlanmaydi.
        """
        if self.is_banned or self.is_deleted:
            return False
        return has_permission(self.role, permission)

    @property
    def is_admin(self) -> bool:
        return self.can(Permission.ADMIN_PANEL)

    @property
    def is_super_admin(self) -> bool:
        return self.role == Role.SUPER_ADMIN.value or self.can(Permission.ADMIN_SETTINGS)

    @property
    def is_teacher(self) -> bool:
        return self.can(Permission.TEST_CREATE)

    def touch(self) -> None:
        """Faollik vaqtini yangilaydi."""
        self.last_active_at = utcnow()


class ParentStudentLink(Base, BigIntPK):
    """
    Ota-ona / Repetitor bog'lanishi.

    O'quvchi test yechgach, uning natijalari ushbu Telegram ID'larga
    avtomatik bildirishnoma sifatida yuboriladi.
    """

    __tablename__ = "parent_student_links"
    __table_args__ = (
        Index("ix_parent_links_student_parent", "student_id", "parent_telegram_id"),
        {"comment": "Ota-ona va o'quvchi bog'lanishi"},
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    parent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    relationship_type: Mapped[str] = mapped_column(
        String(32), default="parent", server_default="parent", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    student: Mapped["User"] = relationship(back_populates="parent_links", lazy="selectin")

