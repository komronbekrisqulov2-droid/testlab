"""Katalog repozitoriylari: test, rasm, kategoriya."""

from __future__ import annotations

import secrets

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from core.datetime_utils import utcnow
from infrastructure.database.repository import BaseRepository, Page
from modules.catalog.models import (
    Category,
    Test,
    TestMedia,
    TestStatus,
    TestVisibility,
)

#  Chalkashtiruvchi belgilar (0/O, 1/I/L) ataylab yo'q — foydalanuvchi
#  kodni og'zaki aytganda xato qilmasin
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


class TestRepository(BaseRepository[Test]):
    """Testlar bilan ishlash."""

    model = Test

    # ------------------------------------------------------------------
    #  Kod generatsiyasi
    # ------------------------------------------------------------------

    async def next_number(self) -> int:
        """
        Keyingi qisqa raqamli kod (1, 2, 3...).

        Foydalanuvchi uchun `12` ni yozish `K7M2QP` dan osonroq.

        DIQQAT: bu yerda poyga bo'lishi mumkin — ikki o'qituvchi bir
        vaqtda test yaratsa ikkalasi ham bir xil raqamni oladi. `number`
        ustunida UNIQUE bor, shuning uchun ikkinchisi IntegrityError
        oladi va servis qayta urinib ko'radi.
        """
        highest = await self.session.scalar(select(func.max(Test.number)))
        return int(highest or 0) + 1

    async def unique_code(self, *, tries: int = 20) -> str:
        """Takrorlanmaydigan harfli kod (havola uchun)."""
        for _ in range(tries):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if not await self.exists(code=code):
                return code

        #  Juda kam ehtimol — uzunroq kod bilan kafolatlaymiz
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH + 2))
            if not await self.exists(code=code):
                return code

    # ------------------------------------------------------------------
    #  O'qish
    # ------------------------------------------------------------------

    async def get_full(self, test_id: int) -> Test | None:
        """Testni barcha bog'lanishlari bilan yuklaydi."""
        statement = (
            select(Test)
            .where(Test.id == test_id)
            .options(
                selectinload(Test.author),
                selectinload(Test.category),
                selectinload(Test.media),
            )
        )
        return await self.session.scalar(statement)

    async def get_by_number(self, number: int) -> Test | None:
        if number <= 0:
            return None
        return await self.session.scalar(
            select(Test).where(Test.number == number).limit(1)
        )

    async def get_by_code(self, code: str) -> Test | None:
        clean = (code or "").strip().upper().replace(" ", "")
        if not clean:
            return None
        return await self.session.scalar(
            select(Test).where(func.upper(Test.code) == clean).limit(1)
        )

    async def find(self, raw: str) -> Test | None:
        """
        Foydalanuvchi kiritgan matn bo'yicha topadi.

        Ikkala format ham ishlaydi: `12` (raqamli) va `K7M2QP` (harfli).
        """
        clean = (raw or "").strip()
        if not clean:
            return None

        if clean.isdigit():
            found = await self.get_by_number(int(clean))
            if found is not None:
                return found

        return await self.get_by_code(clean)

    # ------------------------------------------------------------------
    #  Ro'yxatlar
    # ------------------------------------------------------------------

    async def list_by_author(
        self,
        author_id: int,
        *,
        page: int = 1,
        per_page: int = 8,
        status: str | None = None,
    ) -> Page[Test]:
        statement = select(Test).where(Test.author_id == author_id)
        if status is not None:
            statement = statement.where(Test.status == status)
        statement = statement.order_by(Test.created_at.desc())
        return await self.paginate(statement, page=page, per_page=per_page)

    async def count_by_author(self, author_id: int) -> int:
        return await self.count(author_id=author_id)

    async def list_catalog(
        self,
        *,
        page: int = 1,
        per_page: int = 8,
        category_id: int | None = None,
    ) -> Page[Test]:
        """Ochiq testlar katalogi."""
        statement = select(Test).where(
            Test.status == TestStatus.PUBLISHED.value,
            Test.visibility == TestVisibility.PUBLIC.value,
            Test.questions_count > 0,
        )
        if category_id:
            statement = statement.where(Test.category_id == category_id)

        statement = statement.order_by(Test.published_at.desc().nullslast())
        return await self.paginate(statement, page=page, per_page=per_page)

    async def list_all(
        self,
        *,
        page: int = 1,
        per_page: int = 10,
        status: str | None = None,
        query: str | None = None,
    ) -> Page[Test]:
        """Admin uchun — barcha testlar."""
        statement = select(Test).options(selectinload(Test.author))

        if status is not None:
            statement = statement.where(Test.status == status)

        if query:
            clean = query.strip()
            pattern = f"%{clean.lower()}%"
            conditions = [func.lower(Test.title).like(pattern)]
            if clean.isdigit():
                conditions.append(Test.number == int(clean))
            else:
                conditions.append(func.upper(Test.code) == clean.upper())
            statement = statement.where(or_(*conditions))

        statement = statement.order_by(Test.created_at.desc())
        return await self.paginate(statement, page=page, per_page=per_page)

    # ------------------------------------------------------------------
    #  Jadval bo'yicha (fon vazifasi uchun)
    # ------------------------------------------------------------------

    async def list_due_to_open(self, *, limit: int = 100) -> list[Test]:
        """
        Vaqti kelgan, lekin hali qoralama holatidagi testlar.

        O'qituvchi `starts_at` qo'ygan bo'lsa, o'sha payt test o'zi
        ochilishi kerak — o'qituvchi yarim tunda tugma bosib o'tirmasin.
        Kaliti yo'q test ochilmaydi: yechib bo'lmaydigan testni e'lon
        qilish o'quvchini aldash bo'lardi.
        """
        statement = (
            select(Test)
            .where(
                Test.status == TestStatus.DRAFT.value,
                Test.starts_at.is_not(None),
                Test.starts_at <= utcnow(),
                Test.answer_key.is_not(None),
                Test.questions_count > 0,
            )
            .order_by(Test.starts_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_due_to_close(self, *, limit: int = 100) -> list[Test]:
        """Muddati tugagan, lekin hali ochiq turgan testlar."""
        statement = (
            select(Test)
            .where(
                Test.status == TestStatus.PUBLISHED.value,
                Test.ends_at.is_not(None),
                Test.ends_at < utcnow(),
            )
            .order_by(Test.ends_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    #  Yangilash
    # ------------------------------------------------------------------

    async def publish(self, test: Test) -> Test:
        test.status = TestStatus.PUBLISHED.value
        test.published_at = utcnow()
        await self.session.flush()
        return test

    async def archive(self, test: Test) -> Test:
        test.status = TestStatus.ARCHIVED.value
        await self.session.flush()
        return test

    async def increment_views(self, test: Test) -> None:
        test.views += 1
        await self.session.flush()

    async def refresh_stats(self, test: Test) -> None:
        """
        Keshlangan statistikani qayta hisoblaydi.

        `attempts_count` va `avg_score` denormallashtirilgan — katalogni
        ko'rsatishda har test uchun COUNT/AVG so'rov yubormaslik uchun.
        Har bir yakunlangan urinishdan keyin chaqiriladi.
        """
        from modules.assessment.models import Attempt, AttemptStatus

        finished = (
            Attempt.test_id == test.id,
            Attempt.status.in_(
                [AttemptStatus.FINISHED.value, AttemptStatus.EXPIRED.value]
            ),
            or_(Attempt.is_practice == False, Attempt.is_practice.is_(None)),
        )

        total = await self.session.scalar(
            select(func.count()).select_from(Attempt).where(*finished)
        )
        average = await self.session.scalar(
            select(func.avg(Attempt.percentage)).where(*finished)
        )

        test.attempts_count = int(total or 0)
        test.avg_score = round(float(average or 0.0), 1)
        await self.session.flush()

    # ------------------------------------------------------------------
    #  Statistika
    # ------------------------------------------------------------------

    async def stats(self) -> dict[str, int]:
        """Admin dashboard uchun."""
        total = await self.session.scalar(select(func.count()).select_from(Test))
        published = await self.session.scalar(
            select(func.count())
            .select_from(Test)
            .where(Test.status == TestStatus.PUBLISHED.value)
        )
        drafts = await self.session.scalar(
            select(func.count())
            .select_from(Test)
            .where(Test.status == TestStatus.DRAFT.value)
        )
        return {
            "total": int(total or 0),
            "published": int(published or 0),
            "drafts": int(drafts or 0),
        }


class TestMediaRepository(BaseRepository[TestMedia]):
    """Test varaqasi rasmlari."""

    model = TestMedia

    async def list_by_test(self, test_id: int) -> list[TestMedia]:
        result = await self.session.execute(
            select(TestMedia)
            .where(TestMedia.test_id == test_id)
            .order_by(TestMedia.order_index)
        )
        return list(result.scalars().all())

    async def count_by_test(self, test_id: int) -> int:
        return await self.count(test_id=test_id)

    async def next_order(self, test_id: int) -> int:
        highest = await self.session.scalar(
            select(func.max(TestMedia.order_index)).where(TestMedia.test_id == test_id)
        )
        return int(highest or 0) + 1

    async def has_file(self, test_id: int, file_unique_id: str | None) -> bool:
        """
        Shu rasm allaqachon qo'shilganmi?

        Telegram albom yuborganda ba'zan bir rasm ikki marta keladi —
        dublikat qo'shilmasligi uchun tekshiramiz.
        """
        if not file_unique_id:
            return False

        found = await self.session.scalar(
            select(TestMedia.id)
            .where(
                TestMedia.test_id == test_id,
                TestMedia.file_unique_id == file_unique_id,
            )
            .limit(1)
        )
        return found is not None

    async def add_photo(
        self,
        *,
        test_id: int,
        file_id: str,
        file_unique_id: str | None = None,
        media_type: str = "photo",
        caption: str | None = None,
    ) -> TestMedia | None:
        """Rasm qo'shadi. Dublikat bo'lsa None."""
        if await self.has_file(test_id, file_unique_id):
            return None

        return await self.create(
            test_id=test_id,
            order_index=await self.next_order(test_id),
            file_id=file_id,
            file_unique_id=file_unique_id,
            media_type=media_type,
            caption=(caption or "").strip()[:256] or None,
        )

    async def remove_last(self, test_id: int) -> bool:
        """Oxirgi rasmni o'chiradi."""
        images = await self.list_by_test(test_id)
        if not images:
            return False
        await self.remove(images[-1])
        return True


class CategoryRepository(BaseRepository[Category]):
    """Kategoriyalar."""

    model = Category

    async def list_active(self) -> list[Category]:
        result = await self.session.execute(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.order_index, Category.name)
        )
        return list(result.scalars().all())

    async def seed_defaults(self) -> int:
        """
        Boshlang'ich kategoriyalarni qo'shadi (bo'sh bazada).

        Returns:
            Qo'shilgan kategoriyalar soni.
        """
        from modules.catalog.models import DEFAULT_CATEGORIES

        existing = await self.count()
        if existing > 0:
            return 0

        for index, (name, emoji) in enumerate(DEFAULT_CATEGORIES, start=1):
            self.session.add(Category(name=name, emoji=emoji, order_index=index))

        await self.session.flush()
        return len(DEFAULT_CATEGORIES)
