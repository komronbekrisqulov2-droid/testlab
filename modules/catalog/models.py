"""
Test katalogi: kategoriya, test, test rasmlari.

Test — bu VARAQA RASMI va JAVOBLAR KALITI. Savol matni saqlanmaydi:
o'quvchi rasmni ko'radi, javoblarini bitta xabarda yuboradi.

25 savolli test uchun 25 ta savol + 100 ta variant yozuvi yaratish
ma'nosiz bo'lardi — savol matni ham, variant matni ham yo'q, faqat
to'g'ri harf ma'lum. Shuning uchun butun test BITTA qatorda saqlanadi
(`answer_key = "cbadc..."`).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.datetime_utils import utcnow
from infrastructure.database.base import (
    Base,
    BigIntPK,
    CreatedAtMixin,
    IntPK,
    TimestampMixin,
)

if TYPE_CHECKING:
    from modules.assessment.models import Attempt
    from modules.classroom.models import Classroom
    from modules.identity.models import User


# ======================================================================
#  SANAB O'TILADIGANLAR
# ======================================================================

class TestStatus(StrEnum):
    DRAFT = "draft"            # qoralama
    PUBLISHED = "published"    # yechish mumkin
    ARCHIVED = "archived"      # yopilgan


class TestVisibility(StrEnum):
    PUBLIC = "public"      # katalogda ko'rinadi
    LINK = "link"          # faqat kod bilan
    PRIVATE = "private"    # faqat muallif


#  Javob kalitida ruxsat etilgan harflar
ANSWER_LETTERS: str = "abcdefgh"

STATUS_LABELS: dict[str, str] = {
    TestStatus.DRAFT.value: "📝 Qoralama",
    TestStatus.PUBLISHED.value: "🟢 Ochiq",
    TestStatus.ARCHIVED.value: "📦 Arxiv",
}


# ======================================================================
#  KATEGORIYA
# ======================================================================

class Category(Base, IntPK, TimestampMixin):
    """Test kategoriyasi (fan)."""

    __tablename__ = "categories"
    __table_args__ = ({"comment": "Test kategoriyalari"},)

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    emoji: Mapped[str] = mapped_column(String(8), default="📚", nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )

    tests: Mapped[list["Test"]] = relationship(back_populates="category")

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}"


DEFAULT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Matematika", "🔢"),
    ("Ona tili", "📖"),
    ("Ingliz tili", "🇬🇧"),
    ("Rus tili", "🇷🇺"),
    ("Tarix", "🏛"),
    ("Geografiya", "🌍"),
    ("Biologiya", "🧬"),
    ("Kimyo", "⚗️"),
    ("Fizika", "⚛️"),
    ("Informatika", "💻"),
    ("Dasturlash", "👨‍💻"),
    ("Umumiy bilim", "🧠"),
    ("Boshqa", "📦"),
)


# ======================================================================
#  TEST
# ======================================================================

class Test(Base, IntPK, TimestampMixin):
    """
    Test va uni yechish qoidalari.

    Ikki rejim bir jadvalda saqlanadi:

      * KEY rejimida `answer_key` to'ldiriladi, `questions` bo'sh qoladi.
        25 savolli test uchun 25 ta savol + 100 ta variant yozuvi
        yaratish ma'nosiz — savol matni ham, variant matni ham yo'q,
        faqat to'g'ri harf ma'lum.

      * INTERACTIVE rejimida aksincha: `questions` to'ldiriladi.
    """

    __tablename__ = "tests"
    __table_args__ = (
        Index("ix_tests_author_status", "author_id", "status"),
        Index("ix_tests_status_visibility", "status", "visibility"),
        Index("ix_tests_category_status", "category_id", "status"),
        {"comment": "Testlar"},
    )

    # --- Identifikatorlar ---
    number: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        doc="Qisqa raqamli kod: o'quvchi botga shuni yozadi (12, 13...)",
    )
    code: Mapped[str] = mapped_column(
        String(12),
        unique=True,
        nullable=False,
        index=True,
        doc="Harfli kod (havola uchun): K7M2QP",
    )

    # --- Asosiy ---
    title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # --- Holati ---
    status: Mapped[str] = mapped_column(
        String(16),
        default=TestStatus.DRAFT.value,
        server_default=TestStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    visibility: Mapped[str] = mapped_column(
        String(16),
        default=TestVisibility.LINK.value,
        server_default=TestVisibility.LINK.value,
        nullable=False,
        index=True,
    )

    # --- Javoblar kaliti (KEY rejimi) ---
    answer_key: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        doc="To'g'ri javoblar, kichik harflarda: 'cbadc...'",
    )

    # --- Yechish qoidalari ---
    questions_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    time_limit_sec: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False, doc="0 = cheksiz"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False, doc="0 = cheksiz"
    )
    pass_score: Mapped[int] = mapped_column(
        Integer, default=60, server_default="60", nullable=False
    )
    show_answers: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False,
        doc="Natijada to'g'ri javoblarni ko'rsatish",
    )
    certificate_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    allow_practice: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False,
        doc="O'quvchi 1-rasmiy urinishdan so'ng cheksiz mashq qilib yechishi mumkinmi",
    )

    # --- Randomizatsiya (Ko'chirishga qarshi) ---
    is_randomized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False,
        doc="Savollarni aralashtirish (har bir o'quvchiga har xil tartib)",
    )
    random_questions_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        doc="Barcha savollardan faqat N tasini tasodifiy tanlash (None = barchasi)",
    )

    # --- Sinf / Guruh integratsiyasi ---
    classroom_id: Mapped[int | None] = mapped_column(
        ForeignKey("classrooms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Faqat ma'lum bir sinf/guruh uchun yopiq test",
    )

    # --- Jadval ---
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Kanal/Guruh integratsiyasi ---
    channel_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, doc="E'lon qilingan kanal yoki guruh ID'si"
    )
    channel_message_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, doc="Kanalga yuborilgan xabar ID'si"
    )
    results_posted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, doc="Natijalar kanalga e'lon qilingan vaqt"
    )

    # --- Keshlangan statistika ---
    #  Ataylab denormallashtirilgan: katalogni ko'rsatishda har test uchun
    #  COUNT/AVG so'rov yubormaslik uchun. Yozish paytida yangilanadi.
    views: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    attempts_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    avg_score: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0", nullable=False
    )

    # --- Bog'lanishlar ---
    author: Mapped["User | None"] = relationship(
        back_populates="tests", foreign_keys=[author_id], lazy="selectin"
    )
    category: Mapped["Category | None"] = relationship(
        back_populates="tests", lazy="selectin"
    )
    media: Mapped[list["TestMedia"]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TestMedia.order_index",
        lazy="selectin",
    )
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    explanations: Mapped[list["QuestionExplanation"]] = relationship(
        back_populates="test",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionExplanation.question_number",
        lazy="selectin",
    )
    classroom: Mapped["Classroom | None"] = relationship(
        back_populates="tests",
        lazy="selectin",
    )


    # ------------------------------------------------------------------
    #  Xossalar
    # ------------------------------------------------------------------

    @property
    def is_published(self) -> bool:
        return self.status == TestStatus.PUBLISHED.value

    @property
    def is_draft(self) -> bool:
        return self.status == TestStatus.DRAFT.value

    @property
    def key_letters(self) -> str:
        """Javoblar kaliti (kichik harflarda)."""
        return (self.answer_key or "").strip().lower()

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, "❔")

    def _loaded(self, name: str) -> bool:
        """
        Bog'lanish allaqachon yuklanganmi?

        NIMA UCHUN KERAK
        ----------------
        `lazy="selectin"` faqat SELECT paytida ishlaydi. Yangi yaratilgan
        obyektda (INSERT dan keyin) bog'lanish BO'SH qoladi. Async
        sessiyada bo'sh bog'lanishga murojaat qilish sinxron IO'ni ishga
        tushiradi va `MissingGreenlet` xatosi bilan butun handler'ni
        yiqitadi.

        Shu sababli matn xossalari IO qilmaydi — yuklanmagan bo'lsa
        neytral qiymat qaytaradi. To'g'ri qiymat kerak bo'lsa chaqiruvchi
        `repository.refresh(test, "author", "category", "media")` qiladi.
        """
        from sqlalchemy import inspect as sa_inspect

        return name not in sa_inspect(self).unloaded

    @property
    def author_name(self) -> str:
        if not self._loaded("author"):
            return "—"
        return self.author.full_name if self.author else "—"

    @property
    def category_label(self) -> str:
        if not self._loaded("category"):
            return "📦 Kategoriyasiz"
        return self.category.label if self.category else "📦 Kategoriyasiz"

    @property
    def media_count(self) -> int:
        """Rasmlar soni. Bog'lanish yuklanmagan bo'lsa 0 (IO qilmaydi)."""
        if not self._loaded("media"):
            return 0
        return len(self.media)

    @property
    def not_started_yet(self) -> bool:
        return self.starts_at is not None and utcnow() < self.starts_at

    @property
    def already_ended(self) -> bool:
        return self.ends_at is not None and utcnow() > self.ends_at

    @property
    def is_open(self) -> bool:
        """Hozir yechish mumkinmi?"""
        return (
            self.is_published
            and self.questions_count > 0
            and not self.not_started_yet
            and not self.already_ended
        )

    def closed_reason(self) -> str | None:
        """Yechib bo'lmasa — sababi (o'zbekcha matn)."""
        if self.is_draft:
            return "Bu test hali e'lon qilinmagan."
        if self.status == TestStatus.ARCHIVED.value:
            return "Bu test arxivlangan."
        if self.questions_count == 0:
            return "Bu testda savollar yo'q."
        if self.not_started_yet:
            from core.datetime_utils import fmt_datetime
            return f"Test {fmt_datetime(self.starts_at)} da ochiladi."
        if self.already_ended:
            return "Test muddati tugagan."
        return None


# ======================================================================
#  TEST RASMLARI
# ======================================================================

class TestMedia(Base, IntPK, CreatedAtMixin):
    """
    Test varaqasining rasmi.

    Rasm Telegram serverida qoladi, bizda faqat `file_id`. Bu diskni
    ham, trafikni ham tejaydi.

    ⚠️ `file_id` faqat SHU bot uchun amal qiladi. Token almashtirilsa
    barcha rasmlar yo'qoladi — shuning uchun `storage_key` maydoni bor:
    kelajakda S3/MinIO ga nusxa saqlanadi va kesh yaroqsiz bo'lsa
    fayldan qayta yuklanadi.
    """

    __tablename__ = "test_media"
    __table_args__ = (
        UniqueConstraint("test_id", "order_index", name="uq_test_media_test_order"),
        Index("ix_test_media_test_order", "test_id", "order_index"),
        {"comment": "Test varaqasi rasmlari"},
    )

    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    file_unique_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, doc="Dublikatni aniqlash uchun"
    )
    media_type: Mapped[str] = mapped_column(
        String(16), default="photo", server_default="photo", nullable=False,
        doc="photo / document",
    )
    storage_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, doc="S3/MinIO kaliti (zaxira nusxa)"
    )
    caption: Mapped[str | None] = mapped_column(String(256), nullable=True)

    test: Mapped["Test"] = relationship(back_populates="media")


class QuestionExplanation(Base, BigIntPK):
    """
    Savol yechimi / tushuntirishi.

    O'qituvchi har bir savolga tushuntirish matni yoki rasm/video
    biriktirishi mumkin.
    """

    __tablename__ = "question_explanations"
    __table_args__ = (
        Index("ix_question_explanations_test_qnum", "test_id", "question_number"),
        {"comment": "Savollar yechimlari va tushuntirishlari"},
    )

    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation_text: Mapped[str] = mapped_column(Text, nullable=False)
    media_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    media_type: Mapped[str] = mapped_column(
        String(16), default="text", server_default="text", nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    test: Mapped["Test"] = relationship(back_populates="explanations")


class QuestionAppeal(Base, BigIntPK):
    """
    O'quvchining savol yuzasidan e'tirozi / apellyatsiyasi.
    """

    __tablename__ = "question_appeals"
    __table_args__ = (
        Index("ix_question_appeals_test_qnum", "test_id", "question_number"),
        Index("ix_question_appeals_user", "user_id"),
        {"comment": "Savollar yuzasidan e'tiroz va apellyatsiyalar"},
    )

    test_id: Mapped[int] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    appeal_text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    test: Mapped["Test"] = relationship(lazy="selectin")
    user: Mapped["User"] = relationship(lazy="selectin")

