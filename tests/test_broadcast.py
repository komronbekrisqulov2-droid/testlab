"""
Majburiy obuna va ommaviy xabar sinovi.

NEGA BU SINOV BOR
-----------------
Ikkala funksiya ham «hammaga ta'sir qiladigan» turkumdan:

  * Obuna tekshiruvi noto'g'ri ishlasa, butun bot hamma uchun
    qulflanib qoladi. Shuning uchun eng muhim tekshiruv — Telegram
    javob bermaganda bot O'TKAZIB YUBORISHI (fail-open) kerakligi.

  * Ommaviy xabarni orqaga qaytarib bo'lmaydi. Kimga yuborilishi
    xato hisoblansa, bloklangan yoki bildirishnomani o'chirgan
    odamlarga ham borib qoladi.

Ishga tushirish:
    python tests/test_broadcast.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#  ⚠️ MUHIM: engine importidan OLDIN — sinov ALOHIDA bazani ishlatadi,
#  aks holda ishlaydigan botning ma'lumotlari o'chib ketadi.
from tests import _env  # noqa: F401,E402

from aiogram.exceptions import TelegramRetryAfter  # noqa: E402
from aiogram.methods import GetMe  # noqa: E402
from aiogram.types import TelegramObject  # noqa: E402
from aiogram.types import User as TgUser  # noqa: E402

from apps.bot.handlers.admin import broadcast as bc  # noqa: E402
from apps.bot.keyboards.inline import subscription_keyboard  # noqa: E402
from apps.bot.middlewares.subscription import SubscriptionMiddleware  # noqa: E402
from apps.bot.texts import uz  # noqa: E402
from core.security.permissions import Role  # noqa: E402
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.identity.repository import UserRepository  # noqa: E402
from modules.registry import Base  # noqa: E402

ADMIN_ID = 900_001
STUDENT_ID = 900_002

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


def check_true(label: str, value: bool) -> None:
    check(label, bool(value), True)


# ======================================================================
#  SOXTA TELEGRAM
# ======================================================================

class StubBot:
    """
    `get_chat_member` va `copy_message` ni taqlid qiladi.

    `statuses` — {kanal: holat}. «error» bo'lsa Telegram xato bergani
    (bot kanalda admin emas, kanal o'chirilgan) taqlid qilinadi.
    """

    def __init__(self, statuses: dict[str, str]) -> None:
        self.statuses = statuses
        self.member_calls = 0
        self.copied: list[int] = []
        self.fail_for: set[int] = set()
        self.retry_once_for: set[int] = set()

    async def get_chat_member(self, chat: str, user_id: int) -> Any:
        self.member_calls += 1

        status = self.statuses.get(chat, "member")
        if status == "error":
            raise RuntimeError("bot kanalda admin emas")

        return SimpleNamespace(status=status)

    async def copy_message(self, *, chat_id: int, from_chat_id: int, message_id: int) -> Any:
        if chat_id in self.retry_once_for:
            self.retry_once_for.discard(chat_id)
            raise TelegramRetryAfter(method=GetMe(), message="flood", retry_after=0)

        if chat_id in self.fail_for:
            raise RuntimeError("bot bloklangan")

        self.copied.append(chat_id)
        return SimpleNamespace(message_id=1)


class StubStatus:
    """Jarayon xabari."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def edit_text(self, text: str, **kwargs: Any) -> None:
        self.texts.append(text)


def make_middleware(channels: tuple[str, ...], statuses: dict[str, str]):
    """Middleware va unga mos soxta bot."""
    middleware = SubscriptionMiddleware()
    middleware.channels = channels
    middleware.enabled = bool(channels)
    return middleware, StubBot(statuses)


async def run_middleware(middleware, bot, telegram_id: int) -> bool:
    """
    Middleware'ni bir marta ishlatadi.

    Returns:
        Handler chaqirildimi (ya'ni foydalanuvchi o'tkazildimi).
    """
    passed = False

    async def handler(event: Any, data: dict[str, Any]) -> str:
        nonlocal passed
        passed = True
        return "OK"

    #  Hodisa sifatida `TelegramObject` — u na Message, na CallbackQuery,
    #  demak qulf ekrani chizilmaydi va tarmoqqa chiqilmaydi. Bizni
    #  bu yerda faqat O'TKAZDIMI degan savol qiziqtiradi.
    data = {
        "event_from_user": TgUser(id=telegram_id, is_bot=False, first_name="Sinov"),
        "bot": bot,
    }
    await middleware(handler, TelegramObject(), data)
    return passed


async def main() -> int:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    # ==================================================================
    print("\n--- 1. Kanal ko'rsatilmagan bo'lsa tekshiruv yo'q ---")
    middleware, bot = make_middleware((), {})

    check("o'tkazildi", await run_middleware(middleware, bot, STUDENT_ID), True)
    check("Telegram'ga so'rov yuborilmadi", bot.member_calls, 0)

    # ==================================================================
    print("\n--- 2. A'zo bo'lmagan to'xtatiladi ---")
    middleware, bot = make_middleware(("@kanal1", "@kanal2"), {"@kanal2": "left"})

    check("to'xtatildi", await run_middleware(middleware, bot, STUDENT_ID), False)
    check("ikkala kanal tekshirildi", bot.member_calls, 2)

    # ==================================================================
    print("\n--- 3. A'zo bo'lgan o'tkaziladi va keshlanadi ---")
    middleware, bot = make_middleware(("@kanal1", "@kanal2"), {})

    check("o'tkazildi", await run_middleware(middleware, bot, STUDENT_ID), True)
    check("so'rovlar yuborildi", bot.member_calls, 2)

    #  Ikkinchi murojaatda Telegram'ga umuman chiqilmasligi kerak
    check("qayta o'tkazildi", await run_middleware(middleware, bot, STUDENT_ID), True)
    check("kesh ishladi — yangi so'rov yo'q", bot.member_calls, 2)

    # ==================================================================
    print("\n--- 4. Manfiy javob keshlanmaydi ---")
    middleware, bot = make_middleware(("@kanal1",), {"@kanal1": "left"})

    await run_middleware(middleware, bot, STUDENT_ID)
    before = bot.member_calls

    #  Foydalanuvchi endigina obuna bo'ldi — darhol o'tishi kerak,
    #  kesh muddati tugashini kutmasdan
    bot.statuses["@kanal1"] = "member"

    check("obuna bo'lgach darhol o'tdi",
          await run_middleware(middleware, bot, STUDENT_ID), True)
    check_true("qayta so'raldi", bot.member_calls > before)

    # ==================================================================
    print("\n--- 5. Telegram xato bersa bot qulflanmaydi ---")
    middleware, bot = make_middleware(("@kanal1",), {"@kanal1": "error"})

    #  Sozlama xatosi (bot kanalda admin emas) tufayli BUTUN bot
    #  ishlamay qolishi mumkin emas
    check("xatoda o'tkazildi", await run_middleware(middleware, bot, STUDENT_ID), True)

    # ==================================================================
    print("\n--- 6. Kanal havolasi va nomi ---")
    check("@ bilan", uz.channel_link("@testlab"), "https://t.me/testlab")
    check("@ siz", uz.channel_link("testlab"), "https://t.me/testlab")
    check("to'liq havola", uz.channel_link("https://t.me/testlab"), "https://t.me/testlab")
    check("yopiq kanal ID", uz.channel_link("-1001234567890"), None)
    check("yopiq kanal nomi", uz.channel_label("-1001234567890"), "Yopiq kanal")

    keyboard = subscription_keyboard(["@ochiq", "-1001234567890"])
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    #  Havolasi yo'q kanal uchun tugma qo'yilmaydi — ishlamaydigan
    #  tugma ko'rsatgandan ko'ra ko'rsatmagan afzal
    check("2 ta tugma (1 kanal + tekshirish)", len(buttons), 2)
    check("tekshirish tugmasi oxirida", buttons[-1].text, uz.BTN_CHECK_SUBSCRIPTION)

    text = uz.subscription_required(["@ochiq", "-1001234567890"])
    check_true("ikkala kanal matnda", "@ochiq" in text and "Yopiq kanal" in text)

    # ==================================================================
    print("\n--- 7. Ommaviy xabar kimga boradi ---")
    async with session_factory() as session:
        users = UserRepository(session)

        async def add(telegram_id: int, role: str, **flags) -> None:
            user, _ = await users.get_or_create(telegram_id, first_name=f"U{telegram_id}")
            user.role = role
            user.is_registered = True
            for field, value in flags.items():
                setattr(user, field, value)
            await session.flush()

        await add(1, Role.STUDENT.value)
        await add(2, Role.STUDENT.value)
        await add(3, Role.TEACHER.value)
        await add(4, Role.ADMIN.value)
        await add(5, Role.STUDENT.value, is_banned=True)
        await add(6, Role.STUDENT.value, notifications_enabled=False)

        everyone = await users.list_broadcast_targets()
        check("bloklangan va o'chirganlar chetda", sorted(everyone), [1, 2, 3, 4])

        teachers = await users.list_broadcast_targets(roles=bc.TEACHER_ROLES)
        check("faqat test yaratuvchilar", sorted(teachers), [3, 4])

        await session.commit()

    # ==================================================================
    print("\n--- 8. Yuborish: yetkazilgan va yetkazilmagan ---")
    #  Sinov 0.05 s × 10 = yarim soniya kutmasin
    bc.SEND_DELAY_SEC = 0

    bot = StubBot({})
    bot.fail_for = {3, 7}           # botni bloklaganlar
    bot.retry_once_for = {5}        # Telegram sekinlashtirdi, keyin o'tdi

    status = StubStatus()
    callback = SimpleNamespace(bot=bot)

    sent, failed, elapsed = await bc._deliver(
        callback,
        list(range(1, 11)),
        source_chat_id=ADMIN_ID,
        source_message_id=42,
        status=status,
    )

    check("yetkazildi", sent, 8)
    check("yetkazilmadi", failed, 2)
    check("bloklaganlar chetda qoldi", sorted(bot.copied), [1, 2, 4, 5, 6, 8, 9, 10])
    check_true("vaqt o'lchandi", elapsed >= 0)

    #  Sekinlashtirilgan foydalanuvchi TASHLAB KETILMAYDI — qayta
    #  urinishdan keyin u ham ro'yxatda bo'lishi kerak
    check_true("RetryAfter dan keyin qayta urinildi", 5 in bot.copied)

    # ==================================================================
    print("\n--- 9. Yakuniy hisobot matni ---")
    done = uz.broadcast_done(sent, failed, elapsed)
    check_true("yetkazilganlar soni bor", "8 ta" in done)
    check_true("xatolar soni bor", "2 ta" in done)

    clean = uz.broadcast_done(10, 0, 1.0)
    check_true("xatosiz hisobotda ogohlantirish yo'q", "Yetkazilmadi" not in clean)

    preview = uz.broadcast_preview(1200, "hamma")
    check_true("qabul qiluvchilar soni", "1200 ta" in preview)
    check_true("taxminiy vaqt aytiladi", "Taxminiy vaqt" in preview)

    # ==================================================================
    print()
    if _failures:
        print(f"  {len(_failures)} TA SINOV YIQILDI:")
        for label in _failures:
            print(f"     • {label}")
        return 1

    print("  OBUNA VA OMMAVIY XABAR TO'G'RI")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
