"""
SQLAlchemy asosi: `Base`, mixinlar, portativ tiplar.

Loyiha PostgreSQL uchun mo'ljallangan, lekin mahalliy ishlab chiqishda
SQLite'da ham ishlashi kerak (Postgres o'rnatish shart bo'lmasin).
Shuning uchun tiplar `with_variant` bilan beriladi — SQLAlchemy har bir
baza uchun mos turni o'zi tanlaydi.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, MetaData, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from core.datetime_utils import utcnow

# ----------------------------------------------------------------------
#  Nomlash konvensiyasi
# ----------------------------------------------------------------------
#  Indeks va cheklovlar nomini avtomatik va bir xil qiladi.
#  Alembic uchun MAJBURIY: nomsiz cheklovni SQLite'da o'zgartirib
#  bo'lmaydi (DROP CONSTRAINT nomni talab qiladi).

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# ----------------------------------------------------------------------
#  Portativ tiplar
# ----------------------------------------------------------------------

#  PostgreSQL'da JSONB (indekslanadi, tez), SQLite'da oddiy JSON.
#  Kod ikkalasida ham bir xil ishlaydi.
JSONType = JSON().with_variant(JSONB(), "postgresql")

#  SQLite'da BIGINT autoincrement ishlamaydi — INTEGER kerak.
#  PostgreSQL'da esa BIGINT (BIGSERIAL) kerak: ko'p yozuvli jadvallar
#  2 milliard chegarasiga urilib qolmasin.
BigIntType = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    """Barcha modellar shu klassdan meros oladi."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:
        """Debug uchun o'qishga qulay ko'rinish."""
        interesting = ("id", "telegram_id", "code", "number", "title", "name", "status")
        parts: list[str] = []

        for column in self.__table__.columns:
            if column.name not in interesting:
                continue
            value = getattr(self, column.name, None)
            if value is None:
                continue
            parts.append(f"{column.name}={value!r}")

        return f"<{type(self).__name__} {' '.join(parts)}>"

    def to_dict(self, *, exclude: set[str] | None = None) -> dict[str, object]:
        """Modelni lug'atga o'giradi (eksport va loglar uchun)."""
        skip = exclude or set()
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
            if column.name not in skip
        }


# ----------------------------------------------------------------------
#  Mixinlar
# ----------------------------------------------------------------------

class IntPK:
    """Butun sonli birlamchi kalit (kichik jadvallar uchun)."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class BigIntPK:
    """
    Katta butun sonli birlamchi kalit.

    Urinishlar, javoblar, loglar kabi tez o'sadigan jadvallar uchun.
    """

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)


class TimestampMixin:
    """Yaratilgan va o'zgartirilgan vaqt."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        nullable=False,
        index=True,
        doc="Yaratilgan vaqt (naive UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        doc="Oxirgi o'zgartirilgan vaqt (naive UTC)",
    )


class CreatedAtMixin:
    """
    Faqat yaratilgan vaqt.

    O'zgarmaydigan yozuvlar uchun (log, javob, XP hodisasi) —
    ortiqcha ustun saqlanmaydi.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        nullable=False,
        index=True,
        doc="Yaratilgan vaqt (naive UTC)",
    )


class SoftDeleteMixin:
    """
    Yumshoq o'chirish.

    Yozuv bazadan o'chmaydi, faqat belgilanadi. Foydalanuvchi hisobini
    o'chirganda natijalar va reyting buzilmasligi uchun kerak.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
        doc="O'chirilgan vaqt (None = faol)",
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


__all__ = (
    "Base",
    "IntPK",
    "BigIntPK",
    "TimestampMixin",
    "CreatedAtMixin",
    "SoftDeleteMixin",
    "JSONType",
    "BigIntType",
    "Text",
    "NAMING_CONVENTION",
)
