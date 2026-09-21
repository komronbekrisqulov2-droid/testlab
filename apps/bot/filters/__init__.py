"""
Filtrlar — handler ishga tushishidan oldingi shartlar.

Nega filtr, `if` emas? Chunki filtr handler'ga UMUMAN yetib bormaydi,
ya'ni tekshiruvni unutib qo'yish mumkin emas. `if` bo'lsa yangi handler
yozganda uni qo'shishni unutish oson.
"""

from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.security.permissions import Permission
from modules.identity.models import User


class IsRegistered(Filter):
    """Ro'yxatdan o'tganlar uchun."""

    async def __call__(self, event: TelegramObject, user: User | None = None) -> bool:
        return user is not None and user.is_registered


class HasPermission(Filter):
    """
    Aniq huquqni talab qiladi.

        router.message.filter(HasPermission(Permission.TEST_CREATE))
    """

    def __init__(self, permission: Permission) -> None:
        self.permission = permission

    async def __call__(self, event: TelegramObject, user: User | None = None) -> bool:
        return user is not None and user.can(self.permission)


class IsAdmin(Filter):
    """Admin paneliga kirish huquqi."""

    async def __call__(self, event: TelegramObject, user: User | None = None) -> bool:
        return user is not None and user.can(Permission.ADMIN_PANEL)


class IsPrivate(Filter):
    """
    Faqat shaxsiy chat.

    Guruhga qo'shilgan bot test kodlariga javob berib, guruhni
    to'ldirib yubormasligi kerak.
    """

    async def __call__(self, event: TelegramObject) -> bool:
        if isinstance(event, Message):
            return event.chat.type == "private"
        if isinstance(event, CallbackQuery):
            return event.message is not None and event.message.chat.type == "private"
        return True


__all__ = ("IsRegistered", "HasPermission", "IsAdmin", "IsPrivate")
