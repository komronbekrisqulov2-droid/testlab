"""
Test yaratish va boshqarish — biznes mantiq.

DIQQAT: bu qatlam `aiogram` ni BILMAYDI. Shuning uchun bir xil mantiqni
bot ham, API ham, Mini App ham chaqira oladi.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import (
    ConflictError,
    LimitExceededError,
    PermissionDeniedError,
    TestLabError,
    ValidationError,
)
from core.logging import get_logger
from core.security.permissions import Permission
from modules.catalog.answer_key import (
    count_differences,
    parse_author_key,
    parse_one_line,
)
from modules.catalog.models import Test, TestMedia, TestStatus, TestVisibility
from modules.catalog.repository import (
    CategoryRepository,
    TestMediaRepository,
    TestRepository,
)
from modules.identity.models import User
from modules.identity.repository import UserRepository

log = get_logger(__name__)

#  Bitta testga qo'shsa bo'ladigan rasmlar soni
MAX_MEDIA_PER_TEST = 20

#  Bitta o'qituvchi yarata oladigan testlar soni
MAX_TESTS_PER_AUTHOR = 500

#  Test yaratganlik uchun XP
XP_TEST_CREATED = 25


def _next_copy_title(title: str) -> str:
    """
    Nusxa uchun nom: «Blok-3» -> «Blok-3 (nusxa)» -> «Blok-3 (nusxa 2)».

    Nomlar takrorlanib ketmasligi uchun raqam qo'shiladi.
    """
    import re

    match = re.match(r"^(.*?)\s*\(nusxa(?:\s+(\d+))?\)$", title.strip())

    if match:
        base = match.group(1)
        number = int(match.group(2) or 1) + 1
        return f"{base} (nusxa {number})"[:160]

    return f"{title.strip()} (nusxa)"[:160]


@dataclass(slots=True)
class TestDraft:
    """Yaratilayotgan test haqida qisqa ma'lumot."""

    test: Test
    media_count: int

    @property
    def is_ready(self) -> bool:
        """E'lon qilishga tayyormi?"""
        return bool(self.test.answer_key) and self.test.questions_count > 0


class CatalogService:
    """Testlarni yaratish, tahrirlash, e'lon qilish."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tests = TestRepository(session)
        self.media = TestMediaRepository(session)
        self.categories = CategoryRepository(session)
        self.users = UserRepository(session)

    # ==================================================================
    #  YARATISH
    # ==================================================================

    async def create_from_one_line(self, author: User, raw: str) -> Test:
        """
        Bitta xabardan test yaratadi: `Matematika+abcdabcd`.

        Eng tez usul — o'qituvchi bitta xabar yozadi va test tayyor
        bo'ladi. Darhol e'lon qilinadi: alohida "tasdiqlash" qadami
        hech qanday tanlov bermaydi, faqat ortiqcha bosish qo'shadi.
        """
        self._ensure_can_create(author)

        parsed = parse_one_line(raw, max_questions=settings.test.max_questions)

        test = await self._create_test(
            author,
            title=parsed.title,
            answer_key=parsed.key,
            time_limit_sec=parsed.time_limit_min * 60,
        )

        await self.tests.publish(test)

        log.info(
            "Bir qatorli test: '%s' №%d muallif=%s savollar=%d",
            test.title, test.number, author.telegram_id, test.questions_count,
        )
        return test

    async def create_draft(self, author: User, *, title: str | None = None) -> Test:
        """
        Rasmli test uchun qoralama yaratadi.

        `title` berilmasa "Test №12" avtomatik qo'yiladi. Nomni alohida
        so'rash oqimni uzaytiradi — ko'pchilikka test raqami yetarli.
        Xohlagan o'qituvchi rasmga izoh yozib nom beradi.
        """
        self._ensure_can_create(author)
        return await self._create_test(author, title=title, answer_key=None)

    async def _create_test(
        self,
        author: User,
        *,
        title: str | None,
        answer_key: str | None,
        time_limit_sec: int = 0,
    ) -> Test:
        """
        Testni bazaga yozadi.

        `number` UNIQUE bo'lgani uchun poyga bo'lishi mumkin: ikki
        o'qituvchi bir vaqtda yaratsa ikkinchisi IntegrityError oladi.
        Shuning uchun bir necha marta qayta urinamiz.
        """
        clean_title = (title or "").strip()[:160]
        last_error: Exception | None = None

        for _ in range(5):
            number = await self.tests.next_number()
            code = await self.tests.unique_code()

            try:
                test = await self.tests.create(
                    number=number,
                    code=code,
                    title=clean_title or f"Test №{number}",
                    author_id=author.id,
                    status=TestStatus.DRAFT.value,
                    visibility=TestVisibility.LINK.value,
                    answer_key=answer_key,
                    questions_count=len(answer_key) if answer_key else 0,
                    time_limit_sec=time_limit_sec,
                    pass_score=settings.test.pass_score,
                    max_attempts=settings.test.max_attempts,
                )
            except IntegrityError as error:
                await self.session.rollback()
                last_error = error
                continue

            #  Yangi obyektda bog'lanishlar bo'sh — darhol yuklaymiz,
            #  aks holda `test.author_name` "—" qaytaradi
            await self.tests.refresh(test, "author", "category", "media")
            await self.users.add_xp(author, XP_TEST_CREATED)

            return test

        raise TestLabError(
            "Test raqamini band qilib bo'lmadi.",
            hint="Iltimos, qaytadan urinib ko'ring.",
        ) from last_error

    # ==================================================================
    #  RASMLAR
    # ==================================================================

    async def add_media(
        self,
        test: Test,
        author: User,
        *,
        file_id: str,
        file_unique_id: str | None = None,
        media_type: str = "photo",
        caption: str | None = None,
    ) -> TestMedia | None:
        """
        Test varaqasi rasmini qo'shadi.

        Returns:
            Qo'shilgan rasm, dublikat bo'lsa None.
        """
        self._ensure_owner(test, author)

        current = await self.media.count_by_test(test.id)
        if current >= MAX_MEDIA_PER_TEST:
            raise LimitExceededError(
                f"Ko'pi bilan {MAX_MEDIA_PER_TEST} ta rasm qo'shish mumkin."
            )

        return await self.media.add_photo(
            test_id=test.id,
            file_id=file_id,
            file_unique_id=file_unique_id,
            media_type=media_type,
            caption=caption,
        )

    async def remove_last_media(self, test: Test, author: User) -> bool:
        self._ensure_owner(test, author)
        return await self.media.remove_last(test.id)

    async def media_count(self, test: Test) -> int:
        return await self.media.count_by_test(test.id)

    async def list_media(self, test: Test) -> list[TestMedia]:
        return await self.media.list_by_test(test.id)

    # ==================================================================
    #  KALIT
    # ==================================================================

    async def set_answer_key(self, test: Test, author: User, raw: str) -> Test:
        """
        To'g'ri javoblar kalitini o'rnatadi.

        Savollar soni ALOHIDA so'ralmaydi — kalit uzunligining o'zi
        uni aytadi (25 harf = 25 savol).
        """
        self._ensure_owner(test, author)

        key = parse_author_key(raw)

        if len(key) > settings.test.max_questions:
            raise ValidationError(
                f"Ko'pi bilan {settings.test.max_questions} ta savol bo'lishi mumkin.",
                hint=f"Siz {len(key)} ta javob yubordingiz.",
            )

        test.answer_key = key
        test.questions_count = len(key)
        await self.session.flush()

        log.info("Kalit o'rnatildi: test=№%s savollar=%d", test.number, len(key))
        return test

    async def correct_answer_key(
        self,
        test: Test,
        author: User,
        raw: str,
    ) -> tuple[str, str]:
        """
        Mavjud testning kalitini TUZATADI.

        `set_answer_key` dan farqi: bu yerda test allaqachon e'lon
        qilingan va unga javoblar berilgan bo'lishi mumkin. Shuning
        uchun savollar soni O'ZGARMASLIGI shart — aks holda eski
        javoblar ma'nosini yo'qotadi.

        Natijalarni qayta hisoblash chaqiruvchi tomonda bajariladi
        (`AssessmentService.recalculate_all`), chunki bu servis
        urinishlarni bilmaydi.

        Returns:
            (eski kalit, yangi kalit)
        """
        self._ensure_owner(test, author)

        old_key = test.key_letters
        if not old_key:
            raise ConflictError(
                "Bu testda kalit yo'q.",
                hint="Avval kalitni kiriting.",
            )

        new_key = parse_author_key(raw, expected=len(old_key))

        if new_key == old_key:
            raise ValidationError(
                "Yangi kalit eskisi bilan bir xil.",
                hint="Hech narsa o'zgarmadi.",
            )

        test.answer_key = new_key
        await self.session.flush()

        log.info(
            "Kalit tuzatildi: test=№%s farq=%d ta savol",
            test.number, count_differences(old_key, new_key),
        )
        return old_key, new_key

    # ==================================================================
    #  E'LON QILISH
    # ==================================================================

    async def publish(self, test: Test, author: User) -> Test:
        """Testni yechishga ochadi."""
        self._ensure_owner(test, author)

        problems = await self.readiness_problems(test)
        if problems:
            raise ConflictError(
                "Testni e'lon qilib bo'lmadi.",
                hint="\n".join(f"• {problem}" for problem in problems),
            )

        await self.tests.publish(test)
        log.info("Test e'lon qilindi: №%s '%s'", test.number, test.title)
        return test

    async def readiness_problems(self, test: Test) -> list[str]:
        """
        E'lon qilishga xalaqit berayotgan sabablar.

        DIQQAT: rasm faqat QORALAMA testlarda majburiy. Bir qatorda
        yaratilgan test (`Nom+abcdabcd`) rasmsiz ham to'g'ri — savollar
        og'zaki yoki qog'ozda berilgan bo'lishi mumkin.
        """
        problems: list[str] = []

        if not test.answer_key:
            problems.append("Javoblar kaliti kiritilmagan")

        return problems

    async def archive(self, test: Test, author: User) -> Test:
        self._ensure_owner(test, author)
        return await self.tests.archive(test)

    # ==================================================================
    #  JADVAL BO'YICHA (fon vazifasi)
    # ==================================================================

    async def open_scheduled(self, *, limit: int = 100) -> list[Test]:
        """
        Vaqti kelgan testlarni avtomatik ochadi.

        Egalik tekshirilmaydi — bu foydalanuvchi amali emas, o'qituvchi
        ilgari qo'ygan jadvalning bajarilishi.

        Returns:
            Ochilgan testlar — muallifga xabar berish uchun.
        """
        due = await self.tests.list_due_to_open(limit=limit)

        for test in due:
            await self.tests.publish(test)
            log.info("⏰ Jadval bo'yicha ochildi: №%s '%s'", test.number, test.title)

        return due

    async def close_expired(self, *, limit: int = 100) -> list[Test]:
        """
        Muddati tugagan testlarni avtomatik arxivlaydi.

        NEGA KERAK
        ----------
        `Test.is_open` `ends_at` ni allaqachon tekshiradi, ya'ni javob
        baribir qabul qilinmaydi. Lekin holat `PUBLISHED` bo'lib
        qolaveradi: test katalogda «🟢 Ochiq» deb turadi va o'quvchi
        uni ochib, «muddati tugagan» degan xabarga uriladi. Arxivlash
        ro'yxatni haqiqatga moslaydi.

        Returns:
            Yopilgan testlar — muallifga xabar berish uchun.
        """
        due = await self.tests.list_due_to_close(limit=limit)

        for test in due:
            await self.tests.archive(test)
            log.info("⏰ Muddati tugadi, arxivlandi: №%s '%s'", test.number, test.title)

        return due

    async def delete(self, test: Test, author: User) -> None:
        """Testni butunlay o'chiradi (rasmlar va urinishlar kaskad bilan)."""
        self._ensure_owner(test, author)
        number = test.number
        await self.tests.remove(test)
        log.info("Test o'chirildi: №%s", number)

    # ==================================================================
    #  SOZLAMALAR
    # ==================================================================

    async def update_settings(
        self,
        test: Test,
        author: User,
        *,
        pass_score: int | None = None,
        max_attempts: int | None = None,
        time_limit_min: int | None = None,
        certificate_enabled: bool | None = None,
        show_answers: bool | None = None,
    ) -> Test:
        """
        Test sozlamalarini o'zgartiradi.

        Faqat berilgan maydonlar yangilanadi — qolganiga tegilmaydi.
        Shuning uchun bitta tugma bitta sozlamani almashtira oladi.
        """
        self._ensure_owner(test, author)

        if pass_score is not None:
            if not 0 <= pass_score <= 100:
                raise ValidationError("O'tish balli 0 dan 100 gacha bo'lishi kerak.")
            test.pass_score = pass_score

        if max_attempts is not None:
            if not 0 <= max_attempts <= 100:
                raise ValidationError(
                    "Urinishlar soni 0 dan 100 gacha bo'lishi kerak.",
                    hint="0 — cheksiz.",
                )
            test.max_attempts = max_attempts

        if time_limit_min is not None:
            if not 0 <= time_limit_min <= 600:
                raise ValidationError(
                    "Vaqt 0 dan 600 daqiqagacha bo'lishi kerak.",
                    hint="0 — cheksiz.",
                )
            test.time_limit_sec = time_limit_min * 60

        if certificate_enabled is not None:
            test.certificate_enabled = certificate_enabled

        if show_answers is not None:
            test.show_answers = show_answers

        await self.session.flush()
        return test

    # ==================================================================
    #  NUSXALASH
    # ==================================================================

    async def clone(self, test: Test, author: User) -> Test:
        """
        Testning nusxasini yaratadi.

        Nusxa QORALAMA holatida bo'ladi: o'qituvchi kerak bo'lsa
        kalitni yoki rasmlarni o'zgartirib, keyin e'lon qiladi.

        Rasmlar `file_id` bo'yicha ko'chiriladi — Telegram serveridagi
        bir xil faylga ikkita havola, qo'shimcha joy egallamaydi.
        """
        self._ensure_can_create(author)
        await self.ensure_within_limit(author)

        copy = await self._create_test(
            author,
            title=_next_copy_title(test.title),
            answer_key=test.answer_key,
        )

        #  Sozlamalarni ko'chiramiz
        copy.pass_score = test.pass_score
        copy.max_attempts = test.max_attempts
        copy.time_limit_sec = test.time_limit_sec
        copy.certificate_enabled = test.certificate_enabled
        copy.show_answers = test.show_answers
        copy.category_id = test.category_id
        copy.description = test.description

        #  Rasmlarni ko'chiramiz
        for media in await self.media.list_by_test(test.id):
            await self.media.create(
                test_id=copy.id,
                order_index=media.order_index,
                file_id=media.file_id,
                file_unique_id=None,      # dublikat tekshiruvi yangi testda alohida
                media_type=media.media_type,
                caption=media.caption,
            )

        await self.session.flush()

        log.info("Test nusxalandi: №%s -> №%s", test.number, copy.number)
        return copy

    # ==================================================================
    #  TOPISH
    # ==================================================================

    async def find_for_solving(self, raw: str) -> Test:
        """
        Kod bo'yicha testni topadi va yechish mumkinligini tekshiradi.

        Raises:
            TestNotFoundError / TestNotAvailableError
        """
        from core.exceptions import TestNotAvailableError, TestNotFoundError

        test = await self.tests.find(raw)

        if test is None:
            raise TestNotFoundError(
                f"<b>{raw}</b> kodli test topilmadi.",
                hint="Kodni tekshirib, qaytadan yuboring.",
            )

        reason = test.closed_reason()
        if reason:
            raise TestNotAvailableError(reason)

        return test

    # ==================================================================
    #  TEKSHIRUVLAR
    # ==================================================================

    @staticmethod
    def _ensure_can_create(user: User) -> None:
        if not user.can(Permission.TEST_CREATE):
            raise PermissionDeniedError(
                "Test yaratish uchun o'qituvchi huquqi kerak.",
                hint="Administratorga murojaat qiling.",
            )

    @staticmethod
    def _ensure_owner(test: Test, user: User) -> None:
        """Foydalanuvchi shu testni tahrirlay oladimi?"""
        if test.author_id == user.id:
            return
        if user.can(Permission.TEST_EDIT_ANY):
            return
        raise PermissionDeniedError("Bu test sizga tegishli emas.")

    async def ensure_within_limit(self, author: User) -> None:
        """Test yaratish chegarasi."""
        owned = await self.tests.count_by_author(author.id)
        if owned >= MAX_TESTS_PER_AUTHOR and not author.is_admin:
            raise LimitExceededError(
                f"Siz {MAX_TESTS_PER_AUTHOR} tadan ko'p test yarata olmaysiz.",
                hint="Eski testlarni o'chiring yoki arxivlang.",
            )

    # ==================================================================
    #  SAVOLLAR TUSHUNTIRISHLARI VA YECHIMLARI
    # ==================================================================

    async def set_explanation(
        self,
        test: Test,
        user: User,
        question_number: int,
        text: str,
        media_file_id: str | None = None,
        media_type: str = "text",
    ) -> QuestionExplanation:
        """Savolga yechim / izoh biriktiradi."""
        self._ensure_owner(test, user)

        from sqlalchemy import select
        from modules.catalog.models import QuestionExplanation

        stmt = select(QuestionExplanation).where(
            QuestionExplanation.test_id == test.id,
            QuestionExplanation.question_number == question_number,
        )
        res = await self.session.execute(stmt)
        item = res.scalars().first()
        if item is not None:
            item.explanation_text = text
            item.media_file_id = media_file_id
            item.media_type = media_type
        else:
            item = QuestionExplanation(
                test_id=test.id,
                question_number=question_number,
                explanation_text=text,
                media_file_id=media_file_id,
                media_type=media_type,
            )
            self.session.add(item)

        await self.session.commit()
        return item

    async def get_explanations(self, test_id: int) -> dict[int, QuestionExplanation]:
        """Testning barcha yechimlarini savol raqami bo'yicha lug'at ko'rinishida qaytaradi."""
        from sqlalchemy import select
        from modules.catalog.models import QuestionExplanation

        stmt = select(QuestionExplanation).where(QuestionExplanation.test_id == test_id)
        res = await self.session.execute(stmt)
        return {item.question_number: item for item in res.scalars().all()}

