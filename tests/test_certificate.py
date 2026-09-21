"""
Sertifikat va rasm generatsiyasi sinovlari.

Tekshiradi:
    * sertifikat qoidalari (kimga beriladi, kimga yo'q)
    * takror berilmasligi
    * seriya raqami noyobligi
    * QR havolasi to'g'riligi
    * uchala rasm ham chizilishi (PNG sarlavhasi bilan)
    * motivatsion matn natijaga mos kelishi

Ishga tushirish:
    python tests/test_certificate.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401,E402

from core.config import settings  # noqa: E402
from core.exceptions import ConflictError, NotFoundError  # noqa: E402
from core.security.permissions import Role  # noqa: E402
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.assessment.repository import AttemptRepository  # noqa: E402
from modules.assessment.service import AssessmentService  # noqa: E402
from modules.catalog.service import CatalogService  # noqa: E402
from modules.certification.service import CertificateService  # noqa: E402
from modules.identity.models import User  # noqa: E402
from modules.identity.repository import UserRepository  # noqa: E402
from modules.media import certificate as cert_image  # noqa: E402
from modules.media import fonts, poster, result_card  # noqa: E402
from modules.registry import Base  # noqa: E402

#  PNG fayl har doim shu baytlar bilan boshlanadi
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

KEY = "abcdabcdab"          # 10 savol

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


def check_true(label: str, value: bool) -> None:
    check(label, bool(value), True)


async def expect_error(label: str, coro, error) -> None:
    try:
        await coro
    except error:
        print(f"  OK   {label}")
    except Exception as unexpected:
        print(f"  FAIL {label}\n         kutilgan: {error.__name__}"
              f"\n         olingan : {type(unexpected).__name__}: {unexpected}")
        _failures.append(label)
    else:
        print(f"  FAIL {label} — xato kutilgan edi")
        _failures.append(label)


async def make_user(session, telegram_id, first, last, role) -> User:
    users = UserRepository(session)
    user, _ = await users.get_or_create(telegram_id, first_name=first, last_name=last)
    user.role = role
    user.is_registered = True
    await session.flush()
    return user


# ======================================================================
#  RASMLAR (bazasiz)
# ======================================================================

def test_images() -> None:
    print("\n--- Rasm generatsiyasi ---")

    check_true("TTF shrift topildi", fonts.available())

    card = result_card.render(result_card.ResultCardData(
        student_name="Komronbek Risqulov",
        test_title="Blok-3 · Matematika",
        test_number=12,
        percentage=92.0, correct=23, total=25, wrong=2, skipped=0,
        grade="A+", rank=1, participants=47, passed=True,
        history=(45.0, 60.0, 72.0, 68.0, 81.0, 92.0), streak=5,
    ))
    check_true("kartochka PNG", card.startswith(PNG_MAGIC))
    check_true(f"kartochka hajmi ({len(card):,} bayt)", len(card) > 10_000)

    sheet = poster.render(poster.PosterData(
        test_title="Blok-3 · Matematika",
        test_number=12, questions_count=25,
        author_name="Saxobiddin Karimov",
        category="Matematika", time_limit_min=40, pass_score=60,
    ))
    check_true("poster PNG", sheet.startswith(PNG_MAGIC))

    from core.datetime_utils import utcnow

    cert = cert_image.render(cert_image.CertificateData(
        serial="TL-2026-TEST01",
        holder_name="Komronbek Risqulov",
        test_title="Blok-3 · Matematika",
        percentage=92.0, score=23, max_score=25,
        grade="A+", rank=1, participants=47,
        issued_at=utcnow(),
    ))
    check_true("sertifikat PNG", cert.startswith(PNG_MAGIC))


def test_edge_cases() -> None:
    """Chetki holatlar rasm chizishni buzmasligi kerak."""
    print("\n--- Chetki holatlar ---")

    #  Tarixsiz (birinchi test)
    card = result_card.render(result_card.ResultCardData(
        student_name="A", test_title="T", test_number=1,
        percentage=0.0, correct=0, total=1, wrong=1, skipped=0,
        grade="F", rank=1, participants=1, passed=False,
        history=(), streak=0,
    ))
    check_true("tarixsiz kartochka", card.startswith(PNG_MAGIC))

    #  Juda uzun nom va ism
    card = result_card.render(result_card.ResultCardData(
        student_name="Abdurahmonov Abdurashidbek Abdurahmonovich",
        test_title="Juda uzun test nomi " * 4,
        test_number=999999,
        percentage=100.0, correct=200, total=200, wrong=0, skipped=0,
        grade="A+", rank=1, participants=1000, passed=True,
        history=(100.0,) * 6, streak=99,
    ))
    check_true("uzun matnli kartochka", card.startswith(PNG_MAGIC))

    #  Bir xil natijalar — grafik tekislanib qolmasligi kerak
    card = result_card.render(result_card.ResultCardData(
        student_name="B", test_title="T", test_number=2,
        percentage=70.0, correct=7, total=10, wrong=3, skipped=0,
        grade="B", rank=2, participants=5, passed=True,
        history=(70.0, 70.0, 70.0), streak=3,
    ))
    check_true("bir xil natijalar", card.startswith(PNG_MAGIC))


def test_motivation() -> None:
    print("\n--- Motivatsion matnlar ---")

    check("100%", cert_image.motivation_for(100)[0], "MUKAMMAL NATIJA")
    check("95%", cert_image.motivation_for(95)[0], "MUKAMMAL NATIJA")
    check("92%", cert_image.motivation_for(92)[0], "AJOYIB NATIJA")
    check("78%", cert_image.motivation_for(78)[0], "YAXSHI NATIJA")
    check("64%", cert_image.motivation_for(64)[0], "SIZ O'TDINGIZ")
    check("30%", cert_image.motivation_for(30)[0], "HARAKATINGIZ UCHUN")

    #  Har bir matn keyingi qadamga undashi kerak
    for value in (100, 92, 78, 64, 30):
        _, text = cert_image.motivation_for(value)
        check_true(f"{value}% matni bo'sh emas", len(text) > 40)


# ======================================================================
#  SERTIFIKAT QOIDALARI
# ======================================================================

async def test_certificate_rules() -> int:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    print("\n--- Tayyorgarlik ---")
    async with session_factory() as session:
        teacher = await make_user(session, 100, "Saxobiddin", "Karimov", Role.TEACHER.value)
        await make_user(session, 200, "Komronbek", "Risqulov", Role.STUDENT.value)
        await make_user(session, 300, "Malika", "Ergasheva", Role.STUDENT.value)

        test = await CatalogService(session).create_from_one_line(
            teacher, f"Blok-3 Matematika+{KEY}"
        )
        number = test.number
        await session.commit()
        print(f"  OK   test №{number} yaratildi")

    # ------------------------------------------------------------------
    print("\n--- O'tgan o'quvchiga sertifikat beriladi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        test = await catalog.tests.get_full((await catalog.tests.get_by_number(number)).id)
        student = await UserRepository(session).get_by_telegram_id(200)

        submit = await AssessmentService(session).submit(test, student, "abcdabcdad")
        check("natija 90%", submit.percentage, 90.0)

        service = CertificateService(session)
        allowed, reason = await service.can_issue(submit.attempt, test)
        check("berish mumkin", allowed, True)
        check("sabab yo'q", reason, None)

        certificate = await service.issue(submit.attempt, test, student)
        check("egasi", certificate.holder_name, "Komronbek Risqulov")
        check("test nomi", certificate.test_title, "Blok-3 Matematika")
        check("foiz", certificate.percentage, 90.0)
        check("baho", certificate.grade, "A+")
        check("o'rin", certificate.rank, 1)
        check_true("seriya formati", certificate.serial.startswith("TL-"))

        await session.commit()
        serial = certificate.serial
        attempt_id = submit.attempt.id

    # ------------------------------------------------------------------
    print("\n--- Takror berilmaydi ---")
    async with session_factory() as session:
        service = CertificateService(session)
        attempt = await AttemptRepository(session).get_full(attempt_id)
        student = await UserRepository(session).get_by_telegram_id(200)

        again = await service.issue(attempt, attempt.test, student)
        check("o'sha sertifikat qaytdi", again.serial, serial)

        total = await service.certificates.count()
        check("bazada bitta", total, 1)

    # ------------------------------------------------------------------
    print("\n--- O'tmaganga berilmaydi ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        test = await catalog.tests.get_full((await catalog.tests.get_by_number(number)).id)
        weak = await UserRepository(session).get_by_telegram_id(300)

        submit = await AssessmentService(session).submit(test, weak, "abcd------")
        check("natija 40%", submit.percentage, 40.0)

        service = CertificateService(session)
        allowed, reason = await service.can_issue(submit.attempt, test)
        check("berilmaydi", allowed, False)
        check_true("sabab aytiladi", reason and "60%" in reason)

        await expect_error(
            "issue xato beradi",
            service.issue(submit.attempt, test, weak),
            ConflictError,
        )
        await session.commit()

    # ------------------------------------------------------------------
    print("\n--- Tekshirish (QR kod) ---")
    async with session_factory() as session:
        service = CertificateService(session)

        found = await service.verify(serial)
        check("seriya bo'yicha topildi", found.serial, serial)

        lower = await service.verify(serial.lower())
        check("registrga bog'liq emas", lower.serial, serial)

        await expect_error(
            "yo'q sertifikat",
            service.verify("TL-2026-YOQXXX"),
            NotFoundError,
        )

    # ------------------------------------------------------------------
    print("\n--- Rasm va havola ---")
    async with session_factory() as session:
        service = CertificateService(session)
        certificate = await service.certificates.get_by_serial(serial)

        image = service.render(certificate)
        check_true("sertifikat chizildi", image.startswith(PNG_MAGIC))
        check_true(f"hajmi ({len(image):,} bayt)", len(image) > 20_000)

        name = service.filename(certificate)
        check_true("fayl nomida seriya", serial in name)

        expected_link = settings.bot.deep_link(f"cert_{serial}")
        check_true("QR havolasi to'g'ri", expected_link.endswith(f"start=cert_{serial}"))

    # ------------------------------------------------------------------
    print("\n--- Seriya raqami noyob ---")
    async with session_factory() as session:
        service = CertificateService(session)
        serials = {await service.certificates.generate_serial() for _ in range(50)}
        check("50 ta noyob", len(serials), 50)
        check_true("hammasi TL- bilan", all(s.startswith("TL-") for s in serials))

    await engine.dispose()
    return 0


# ======================================================================

def main() -> int:
    print("\n  TestLab — sertifikat sinovlari")

    test_images()
    test_edge_cases()
    test_motivation()
    asyncio.run(test_certificate_rules())

    print()
    if _failures:
        print(f"  {len(_failures)} ta sinov muvaffaqiyatsiz:")
        for name in _failures:
            print(f"    - {name}")
        return 1

    print("  SERTIFIKAT VA RASMLAR TO'G'RI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
