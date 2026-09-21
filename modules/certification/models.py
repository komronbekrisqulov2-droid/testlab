"""Sertifikat modeli."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base, CreatedAtMixin, IntPK

if TYPE_CHECKING:
    from modules.assessment.models import Attempt
    from modules.catalog.models import Test
    from modules.identity.models import User


class Certificate(Base, IntPK, CreatedAtMixin):
    """
    Berilgan sertifikat.

    NEGA NATIJA NUSXALANADI?
    ------------------------
    `holder_name`, `test_title`, `percentage` va boshqalar bu yerda
    QAYTA saqlanadi, garchi ular `user` va `test` da ham bo'lsa-da.

    Sabab: sertifikat — **hujjat**. U berilgan paytdagi holatni
    ko'rsatishi kerak. Foydalanuvchi ismini o'zgartirsa yoki o'qituvchi
    test nomini tahrirlasa, allaqachon berilgan sertifikat o'zgarmasligi
    lozim — aks holda QR orqali tekshirganda boshqa ma'lumot chiqadi.

    Bitta urinishga bitta sertifikat (`attempt_id` unikal).
    """

    __tablename__ = "certificates"
    __table_args__ = (
        Index("ix_certificates_user_test", "user_id", "test_id"),
        {"comment": "Berilgan sertifikatlar"},
    )

    serial: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
        doc="Noyob raqam: TL-2026-7LZ5W3",
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
        doc="Bitta urinishga bitta sertifikat",
    )

    # --- Berilgan paytdagi holat (o'zgarmaydi) ---
    holder_name: Mapped[str] = mapped_column(String(160), nullable=False)
    test_title: Mapped[str] = mapped_column(String(160), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    grade: Mapped[str] = mapped_column(String(4), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_participants: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # --- Telegram keshi ---
    #  Bir marta chizilgan rasmni qayta chizmaymiz — `file_id` bilan
    #  yuborish bir necha marta tezroq va serverni yuklamaydi.
    file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    document_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # --- Bog'lanishlar ---
    user: Mapped["User"] = relationship(lazy="selectin")
    test: Mapped["Test"] = relationship(lazy="selectin")
    attempt: Mapped["Attempt"] = relationship(lazy="selectin")

    @property
    def issued_at(self) -> datetime:
        """Berilgan vaqt (`created_at` uchun tushunarli nom)."""
        return self.created_at
