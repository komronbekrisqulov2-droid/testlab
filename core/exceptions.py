"""
Domen xatoliklari.

Har bir xato foydalanuvchiga ko'rsatiladigan TAYYOR o'zbekcha matn bilan
keladi — handler faqat `error.message` ni chiqaradi va nima yozishni
o'ylab o'tirmaydi.

Ierarxiya:

    TestLabError
    ├── NotFoundError          — topilmadi
    ├── ValidationError        — kiritilgan ma'lumot noto'g'ri
    ├── PermissionDeniedError  — huquq yo'q
    ├── ConflictError          — holat mos emas
    ├── LimitExceededError     — chegaradan oshdi
    └── ExternalServiceError   — tashqi xizmat (AI, to'lov) javob bermadi
"""

from __future__ import annotations


class TestLabError(Exception):
    """Barcha domen xatoliklarining asosi."""

    default_message = "Kutilmagan xatolik yuz berdi."

    def __init__(self, message: str | None = None, *, hint: str | None = None) -> None:
        self.message = message or self.default_message
        self.hint = hint
        super().__init__(self.message)

    def user_text(self) -> str:
        """Foydalanuvchiga yuboriladigan to'liq matn."""
        if self.hint:
            return f"{self.message}\n\n{self.hint}"
        return self.message


# ----------------------------------------------------------------------
#  Umumiy
# ----------------------------------------------------------------------

class NotFoundError(TestLabError):
    """So'ralgan obyekt topilmadi."""
    default_message = "So'ralgan ma'lumot topilmadi."


class ValidationError(TestLabError):
    """Kiritilgan ma'lumot qoidaga mos emas."""
    default_message = "Kiritilgan ma'lumot noto'g'ri."


class PermissionDeniedError(TestLabError):
    """Foydalanuvchining bu amalga huquqi yo'q."""
    default_message = "Bu amalni bajarishga ruxsatingiz yo'q."


class ConflictError(TestLabError):
    """Obyekt holati amalga mos emas."""
    default_message = "Bu amalni hozirgi holatda bajarib bo'lmaydi."


class LimitExceededError(TestLabError):
    """Chegaradan oshib ketildi."""
    default_message = "Belgilangan chegaradan oshib ketdingiz."


class ExternalServiceError(TestLabError):
    """Tashqi xizmat javob bermadi yoki xato qaytardi."""
    default_message = "Tashqi xizmat vaqtincha ishlamayapti. Keyinroq urinib ko'ring."


# ----------------------------------------------------------------------
#  Foydalanuvchi
# ----------------------------------------------------------------------

class UserBannedError(PermissionDeniedError):
    """Foydalanuvchi bloklangan."""
    default_message = "Hisobingiz bloklangan."


class NotSubscribedError(PermissionDeniedError):
    """Majburiy kanallarga obuna bo'lmagan."""
    default_message = "Botdan foydalanish uchun kanallarga a'zo bo'ling."


class NotRegisteredError(TestLabError):
    """Ro'yxatdan o'tmagan."""
    default_message = "Avval ro'yxatdan o'ting."


# ----------------------------------------------------------------------
#  Test
# ----------------------------------------------------------------------

class TestNotFoundError(NotFoundError):
    default_message = "Bunday kodli test topilmadi."


class TestNotAvailableError(ConflictError):
    default_message = "Bu test hozir yechish uchun ochiq emas."


class AlreadyAnsweredError(ConflictError):
    default_message = "Siz bu testga allaqachon javob bergansiz."


class AnswerKeyError(ValidationError):
    """Javoblar kalitini o'qib bo'lmadi."""
    default_message = "Javoblarni o'qiy olmadim."
