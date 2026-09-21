"""
Asosiy repozitoriy — umumiy CRUD va sahifalash.

Har bir modul o'z repozitoriysini shundan meros oladi va faqat
o'ziga xos so'rovlarni qo'shadi. Takrorlanadigan kod bir joyda turadi.

QOIDA: SQL faqat repozitoriyda yoziladi. Servis ham, handler ham
`select()` chaqirmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


@dataclass(slots=True)
class Page(Generic[ModelT]):
    """Sahifalangan natija."""

    items: list[ModelT]
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        """Jami sahifalar soni (kamida 1)."""
        if self.per_page <= 0:
            return 1
        return max(1, ceil(self.total / self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def start_index(self) -> int:
        """Shu sahifadagi birinchi element tartib raqami (0 dan)."""
        return (self.page - 1) * self.per_page

    @property
    def is_empty(self) -> bool:
        return self.total == 0


class BaseRepository(Generic[ModelT]):
    """Umumiy CRUD amallari."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    #  O'qish
    # ------------------------------------------------------------------

    async def get(self, entity_id: int) -> ModelT | None:
        """ID bo'yicha topadi."""
        return await self.session.get(self.model, entity_id)

    async def get_by(self, **filters: Any) -> ModelT | None:
        """Berilgan shartlar bo'yicha bittasini topadi."""
        statement = select(self.model).filter_by(**filters).limit(1)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by(self, *, limit: int | None = None, **filters: Any) -> list[ModelT]:
        """Shartlarga mos yozuvlar ro'yxati."""
        statement = select(self.model).filter_by(**filters)
        if limit is not None:
            statement = statement.limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def exists(self, **filters: Any) -> bool:
        """Bunday yozuv bormi? (butun obyektni yuklamaydi)"""
        statement = select(self.model.id).filter_by(**filters).limit(1)  # type: ignore[attr-defined]
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def count(self, **filters: Any) -> int:
        """Shartlarga mos yozuvlar soni."""
        statement = select(func.count()).select_from(self.model)
        if filters:
            statement = statement.filter_by(**filters)
        return int(await self.session.scalar(statement) or 0)

    # ------------------------------------------------------------------
    #  Sahifalash
    # ------------------------------------------------------------------

    async def paginate(
        self,
        statement: Select[Any],
        *,
        page: int = 1,
        per_page: int = 10,
    ) -> Page[ModelT]:
        """
        Tayyor so'rovni sahifalab qaytaradi.

        Jami sonni alohida `COUNT` bilan oladi — bu `LIMIT`/`OFFSET`
        dan oldin bajarilishi kerak, aks holda noto'g'ri son chiqadi.
        """
        page = max(1, page)
        per_page = max(1, per_page)

        #  Tartiblash COUNT uchun keraksiz va PostgreSQL'da xatoga
        #  olib kelishi mumkin — olib tashlaymiz
        count_statement = select(func.count()).select_from(
            statement.order_by(None).subquery()
        )
        total = int(await self.session.scalar(count_statement) or 0)

        offset = (page - 1) * per_page
        result = await self.session.execute(statement.limit(per_page).offset(offset))

        return Page(
            items=list(result.scalars().all()),
            total=total,
            page=page,
            per_page=per_page,
        )

    # ------------------------------------------------------------------
    #  Yozish
    # ------------------------------------------------------------------

    async def create(self, **values: Any) -> ModelT:
        """
        Yangi yozuv yaratadi va `flush` qiladi — ID darhol tayyor bo'ladi.

        `commit` qilinmaydi: uni middleware yoki `get_session` bajaradi.
        Shunday qilib bitta so'rovdagi barcha o'zgarishlar bitta
        tranzaksiyada qoladi.
        """
        instance = self.model(**values)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def add(self, instance: ModelT) -> ModelT:
        """Tayyor obyektni sessiyaga qo'shadi."""
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def add_all(self, instances: Sequence[ModelT]) -> None:
        """Bir nechta obyektni birdan qo'shadi."""
        if not instances:
            return
        self.session.add_all(list(instances))
        await self.session.flush()

    async def update_fields(self, instance: ModelT, **values: Any) -> ModelT:
        """Obyekt maydonlarini yangilaydi."""
        for field, value in values.items():
            setattr(instance, field, value)
        await self.session.flush()
        return instance

    async def bulk_update(self, *, where: Any, **values: Any) -> int:
        """
        Ko'p yozuvni bitta so'rov bilan yangilaydi.

        Returns:
            O'zgargan qatorlar soni.
        """
        result = await self.session.execute(
            update(self.model).where(where).values(**values)
        )
        return int(result.rowcount or 0)

    # ------------------------------------------------------------------
    #  O'chirish
    # ------------------------------------------------------------------

    async def remove(self, instance: ModelT) -> None:
        """Obyektni o'chiradi (bog'liq yozuvlar kaskad bilan ketadi)."""
        await self.session.delete(instance)
        await self.session.flush()

    async def remove_by_id(self, entity_id: int) -> bool:
        """ID bo'yicha o'chiradi. Topilmasa False."""
        instance = await self.get(entity_id)
        if instance is None:
            return False
        await self.remove(instance)
        return True

    async def bulk_delete(self, where: Any) -> int:
        """Shartga mos yozuvlarni o'chiradi. O'chirilgan sonini qaytaradi."""
        result = await self.session.execute(delete(self.model).where(where))
        return int(result.rowcount or 0)

    # ------------------------------------------------------------------
    #  Yordamchi
    # ------------------------------------------------------------------

    async def refresh(self, instance: ModelT, *fields: str) -> ModelT:
        """
        Obyektni bazadan qayta o'qiydi.

        Yangi yaratilgan obyektning bog'lanishlari (relationship) bo'sh
        bo'ladi — `lazy="selectin"` faqat SELECT paytida ishlaydi. Ularga
        murojaat qilishdan oldin shu metod chaqirilishi kerak, aks holda
        async sessiyada `MissingGreenlet` xatosi chiqadi.
        """
        await self.session.refresh(instance, attribute_names=list(fields) or None)
        return instance
