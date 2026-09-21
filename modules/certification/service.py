"""
Sertifikat berish va tekshirish.

Sertifikat — **yakun emas, keyingi qadamga taklif**. Shuning uchun
rasmdagi matn natijaga qarab o'zgaradi va o'quvchini davom etishga
undaydi.
"""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import ConflictError, NotFoundError
from core.logging import get_logger
from infrastructure.database.repository import BaseRepository, Page
from modules.assessment.models import Attempt
from modules.assessment.repository import AttemptRepository
from modules.catalog.models import Test
from modules.certification.models import Certificate
from modules.identity.models import User
from modules.media import certificate as certificate_image

log = get_logger(__name__)

#  Seriya alifbosi — chalkashtiruvchi belgilarsiz (0/O, 1/I)
SERIAL_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
SERIAL_LENGTH = 6


class CertificateRepository(BaseRepository[Certificate]):
    """Sertifikatlar bilan ishlash."""

    model = Certificate

    async def get_by_serial(self, serial: str) -> Certificate | None:
        clean = (serial or "").strip().upper()
        if not clean:
            return None
        return await self.session.scalar(
            select(Certificate).where(func.upper(Certificate.serial) == clean).limit(1)
        )

    async def get_by_attempt(self, attempt_id: int) -> Certificate | None:
        return await self.session.scalar(
            select(Certificate).where(Certificate.attempt_id == attempt_id).limit(1)
        )

    async def list_by_user(
        self,
        user_id: int,
        *,
        page: int = 1,
        per_page: int = 8,
    ) -> Page[Certificate]:
        statement = (
            select(Certificate)
            .where(Certificate.user_id == user_id)
            .order_by(Certificate.created_at.desc())
        )
        return await self.paginate(statement, page=page, per_page=per_page)

    async def generate_serial(self, *, year: int | None = None) -> str:
        """
        Noyob seriya raqami: `TL-2026-7LZ5W3`.

        Yil qo'shilgani sertifikat qachon berilganini raqamning o'zidan
        ko'rsatadi — tekshirishda qulay.
        """
        from core.datetime_utils import utcnow

        current_year = year or utcnow().year

        for _ in range(20):
            code = "".join(secrets.choice(SERIAL_ALPHABET) for _ in range(SERIAL_LENGTH))
            serial = f"TL-{current_year}-{code}"
            if not await self.exists(serial=serial):
                return serial

        #  Juda kam ehtimol — uzunroq kod bilan kafolatlaymiz
        while True:
            code = "".join(
                secrets.choice(SERIAL_ALPHABET) for _ in range(SERIAL_LENGTH + 2)
            )
            serial = f"TL-{current_year}-{code}"
            if not await self.exists(serial=serial):
                return serial

    async def save_file_ids(
        self,
        certificate: Certificate,
        *,
        photo_file_id: str | None = None,
        document_file_id: str | None = None,
    ) -> None:
        """Telegram fayl identifikatorlarini keshlaydi."""
        if photo_file_id:
            certificate.file_id = photo_file_id
        if document_file_id:
            certificate.document_file_id = document_file_id
        await self.session.flush()


class CertificateService:
    """Sertifikat berish, chizish, tekshirish."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.certificates = CertificateRepository(session)
        self.attempts = AttemptRepository(session)

    # ==================================================================
    #  BERISH
    # ==================================================================

    async def can_issue(self, attempt: Attempt, test: Test) -> tuple[bool, str | None]:
        """
        Sertifikat berish mumkinmi (istisno tashlamasdan).

        Returns:
            (mumkinmi, sabab)
        """
        if not test.certificate_enabled:
            return False, "Bu testda sertifikat berish o'chirilgan."

        if not attempt.is_finished:
            return False, "Sertifikat test yakunlangandan keyin beriladi."

        if not attempt.is_passed:
            return False, (
                f"Sertifikat uchun kamida {test.pass_score}% to'plash kerak.\n"
                f"Sizning natijangiz: {attempt.percentage:g}%"
            )

        return True, None

    async def issue(self, attempt: Attempt, test: Test, user: User) -> Certificate:
        """
        Sertifikat yaratadi (yoki mavjudini qaytaradi).

        Takror berilmaydi: bitta urinishga bitta sertifikat.
        """
        existing = await self.certificates.get_by_attempt(attempt.id)
        if existing is not None:
            return existing

        allowed, reason = await self.can_issue(attempt, test)
        if not allowed:
            raise ConflictError(reason or "Sertifikat berib bo'lmadi.")

        rank, participants = await self.attempts.rank_in_test(attempt)
        serial = await self.certificates.generate_serial()

        certificate = await self.certificates.create(
            serial=serial,
            user_id=user.id,
            test_id=test.id,
            attempt_id=attempt.id,
            holder_name=user.full_name,
            test_title=test.title,
            score=attempt.score,
            max_score=attempt.max_score,
            percentage=attempt.percentage,
            grade=attempt.grade or "C",
            rank=rank,
            total_participants=participants,
        )

        log.info(
            "🏅 Sertifikat: %s -> %s (%s%%, %d-o'rin)",
            serial, user.full_name, attempt.percentage, rank,
        )
        return certificate

    # ==================================================================
    #  CHIZISH
    # ==================================================================

    def render(self, certificate: Certificate) -> bytes:
        """Sertifikat rasmini chizadi."""
        return certificate_image.render(self._to_image_data(certificate))

    def filename(self, certificate: Certificate) -> str:
        return certificate_image.filename(self._to_image_data(certificate))

    @staticmethod
    def _to_image_data(certificate: Certificate) -> certificate_image.CertificateData:
        return certificate_image.CertificateData(
            serial=certificate.serial,
            holder_name=certificate.holder_name,
            test_title=certificate.test_title,
            percentage=certificate.percentage,
            score=certificate.score,
            max_score=certificate.max_score,
            grade=certificate.grade,
            rank=certificate.rank,
            participants=certificate.total_participants,
            issued_at=certificate.issued_at,
            verify_link=settings.bot.deep_link(f"cert_{certificate.serial}"),
        )

    # ==================================================================
    #  TEKSHIRISH
    # ==================================================================

    async def verify(self, serial: str) -> Certificate:
        """
        Seriya raqami bo'yicha sertifikatni topadi.

        QR kodni skanerlagan odam shu yerga tushadi.
        """
        certificate = await self.certificates.get_by_serial(serial)

        if certificate is None:
            raise NotFoundError(
                f"<b>{serial}</b> raqamli sertifikat topilmadi.",
                hint="Raqamni tekshirib ko'ring yoki QR kodni qayta skanerlang.",
            )

        return certificate


def motivation_title(percentage: float) -> str:
    """Natijaga mos motivatsion sarlavha (xabar matnida ham ishlatiladi)."""
    return certificate_image.motivation_for(percentage)[0]
