"""
Middleware zanjiri.

TARTIB MUHIM:

    1. Logging      — har bir update yozib boriladi
    2. Throttling   — spam filtri (bazaga tegmasdan)
    3. Database     — sessiya ochiladi/yopiladi
    4. User         — foydalanuvchi yuklanadi, ban tekshiriladi
    5. Subscription — majburiy kanallarga a'zolik

Nega aynan shunday? Throttling bazadan OLDIN turadi — spam so'rov uchun
sessiya ochish isrofgarchilik. User esa bazadan KEYIN, chunki
foydalanuvchini yuklash uchun sessiya kerak.

Subscription ENG OXIRIDA: bloklangan foydalanuvchi obuna ekranini ham
ko'rmasligi kerak (`UserMiddleware` uni allaqachon to'xtatgan), va
tekshiruv `.env` da kanal ko'rsatilmagan bo'lsa umuman ishlamaydi.
"""

from __future__ import annotations

from aiogram import Dispatcher

from apps.bot.middlewares.database import DatabaseMiddleware
from apps.bot.middlewares.logging import LoggingMiddleware
from apps.bot.middlewares.subscription import SubscriptionMiddleware
from apps.bot.middlewares.throttling import ThrottlingMiddleware
from apps.bot.middlewares.user import UserMiddleware
from core.logging import get_logger

log = get_logger(__name__)


def setup_middlewares(dispatcher: Dispatcher) -> None:
    """
    Middleware'larni to'g'ri tartibda ulaydi.

    NEGA `outer_middleware`, `middleware` EMAS?
    -------------------------------------------
    aiogram 3 da ikki xil middleware bor va ular TURLI vaqtda ishlaydi:

        outer_middleware  ->  filtrlardan OLDIN
        middleware        ->  filtrlardan KEYIN, handler'dan oldin

    Bizning router'lar `IsRegistered`, `IsAdmin`, `HasPermission` kabi
    filtrlardan foydalanadi va ular `user` obyektini talab qiladi.
    Agar `UserMiddleware` ichki (inner) bo'lsa, filtr tekshirilayotgan
    paytda `user` hali mavjud emas — filtr `False` qaytaradi va BUTUN
    router chetlab o'tiladi. Natijada hamma narsa `fallback` ga tushib
    "Bu tugma eskirgan" deb chiqadi.

    Shuning uchun ma'lumot beruvchi middleware'lar TASHQI bo'lishi shart.
    """
    chain = (
        LoggingMiddleware(),
        ThrottlingMiddleware(),
        DatabaseMiddleware(),
        UserMiddleware(),
        SubscriptionMiddleware(),
    )

    for middleware in chain:
        dispatcher.message.outer_middleware(middleware)
        dispatcher.callback_query.outer_middleware(middleware)

    log.info("🔗 %d ta middleware ulandi (outer)", len(chain))


__all__ = (
    "setup_middlewares",
    "LoggingMiddleware",
    "ThrottlingMiddleware",
    "DatabaseMiddleware",
    "UserMiddleware",
    "SubscriptionMiddleware",
)
