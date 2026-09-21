"""
Modellar reyestri.

`Base.metadata` faqat import qilingan modellarni ko'radi. Alembic ham,
`create_all` ham shu metadata bilan ishlaydi — shuning uchun HAR BIR
yangi model shu yerga qo'shilishi SHART.

Unutilsa nima bo'ladi? Migratsiya jimgina jadvalni tashlab ketadi va
xato faqat ishlash paytida chiqadi. Shu sababli reyestr alohida faylda
turadi va sinov bilan tekshiriladi.
"""

from __future__ import annotations

from infrastructure.database.base import Base

# --- identity ---
from modules.identity.models import ParentStudentLink, User

# --- catalog ---
from modules.catalog.models import (
    ANSWER_LETTERS,
    DEFAULT_CATEGORIES,
    Category,
    QuestionExplanation,
    Test,
    TestMedia,
    TestStatus,
    TestVisibility,
)

# --- assessment ---
from modules.assessment.models import (
    GRADE_SCALE,
    Attempt,
    AttemptStatus,
    StudentMistake,
    grade_for,
)

# --- certification ---
from modules.certification.models import Certificate

#  Reyestrda bo'lishi kutilayotgan jadvallar.
#  Sinov shu ro'yxat bilan `Base.metadata` ni solishtiradi.
EXPECTED_TABLES: frozenset[str] = frozenset({
    "users",
    "categories",
    "tests",
    "test_media",
    "attempts",
    "certificates",
    "student_mistakes",
    "question_explanations",
    "parent_student_links",
})

__all__ = (
    "Base",
    "EXPECTED_TABLES",
    # identity
    "User",
    "ParentStudentLink",
    # catalog
    "Category",
    "DEFAULT_CATEGORIES",
    "Test",
    "TestMedia",
    "TestStatus",
    "TestVisibility",
    "QuestionExplanation",
    "ANSWER_LETTERS",
    # assessment
    "Attempt",
    "AttemptStatus",
    "StudentMistake",
    "GRADE_SCALE",
    "grade_for",
    # certification
    "Certificate",
)

