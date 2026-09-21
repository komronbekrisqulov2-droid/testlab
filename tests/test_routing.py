"""
Marshrutlash sinovi — xabar/tugma TO'G'RI handler'ga yetib boradimi.

NEGA BU SINOV BOR
-----------------
Domen sinovlari servislarni tekshiradi, lekin update handler'ga
yetib borishini tekshirmaydi. Aynan shu joyda xato bo'lgan edi:

    middleware'lar `middleware()` bilan ulangan edi (ichki), lekin
    router filtrlari (`IsAdmin`, `HasPermission`) filtrlardan OLDIN
    ishlaydigan `outer_middleware()` ni talab qiladi. Natijada `user`
    filtr paytida mavjud emas edi, filtr `False` qaytarardi va BUTUN
    router chetlab o'tilardi — hamma narsa "Bu tugma eskirgan" ga
    tushardi.

Bu sinov `fallback` routerisiz ishlaydi: agar biror update handler
topmasa, aiogram `UNHANDLED` qaytaradi va sinov yiqiladi.

Ishga tushirish:
    python tests/test_routing.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#  ⚠️ MUHIM: engine importidan OLDIN — sinov ALOHIDA bazani ishlatadi,
#  aks holda ishlaydigan botning ma'lumotlari o'chib ketadi.
from tests import _env  # noqa: F401,E402

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.dispatcher.event.bases import UNHANDLED  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import TelegramMethod  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    Message,
    Update,
)
from aiogram.types import User as TgUser  # noqa: E402

from apps.bot.handlers.admin import panel as admin_panel  # noqa: E402
from apps.bot.handlers.shared import access as shared_access  # noqa: E402
from apps.bot.handlers.shared import start as shared_start  # noqa: E402
from apps.bot.handlers.student import answer as student_answer  # noqa: E402
from apps.bot.handlers.teacher import create as teacher_create  # noqa: E402
from apps.bot.handlers.teacher import manage as teacher_manage  # noqa: E402
from apps.bot.keyboards.callbacks import AdminCB, MenuCB  # noqa: E402
from apps.bot.middlewares import setup_middlewares  # noqa: E402
from core.security.permissions import Role  # noqa: E402
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.identity.repository import UserRepository  # noqa: E402
from modules.registry import Base  # noqa: E402

FAKE_TOKEN = "123456789:AAFakeTokenForRoutingTests1234567890"

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
#  TELEGRAM'SIZ SESSIYA
# ======================================================================

class FakeSession(BaseSession):
    """
    Tarmoqqa chiqmaydigan sessiya.

    Har bir API chaqiruvini yozib boradi va ishonarli natija qaytaradi,
    shunda handler'lar odatdagidek ishlaydi.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        name = type(method).__name__
        self.calls.append(name)
        return self._result_for(name)

    @staticmethod
    def _result_for(name: str) -> Any:
        """Metod turiga mos soxta natija."""
        if name in {"GetMe"}:
            return TgUser(id=1, is_bot=True, first_name="TestLab", username="testlab_bot")

        if name.startswith(("SendMessage", "EditMessageText", "SendPhoto", "SendDocument")):
            return Message(
                message_id=1,
                date=datetime.now(),
                chat=Chat(id=ADMIN_ID, type="private"),
            )

        if name == "SendMediaGroup":
            return []

        #  AnswerCallbackQuery, SetMyCommands, DeleteWebhook va h.k.
        return True

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        yield b""

    async def close(self) -> None:
        pass


def make_bot() -> Bot:
    bot = Bot(
        token=FAKE_TOKEN,
        session=FakeSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    return bot


def make_dispatcher() -> Dispatcher:
    """
    Dispatcher — `fallback` routerisiz.

    Fallback bo'lsa u hamma narsani ushlab qolib, sinov har doim
    "o'tdi" derdi. Usiz esa topilmagan update `UNHANDLED` qaytaradi.
    """
    dispatcher = Dispatcher(storage=MemoryStorage())
    setup_middlewares(dispatcher)

    for router in (
        shared_start.router,
        admin_panel.router,
        teacher_create.router,
        teacher_manage.router,
        student_answer.router,
        shared_access.router,
    ):
        dispatcher.include_router(router)

    return dispatcher


# ======================================================================
#  UPDATE YASASH
# ======================================================================

_counter = 0


def next_id() -> int:
    global _counter
    _counter += 1
    return _counter


def message_update(text: str, telegram_id: int) -> Update:
    return Update(
        update_id=next_id(),
        message=Message(
            message_id=next_id(),
            date=datetime.now(),
            chat=Chat(id=telegram_id, type="private"),
            from_user=TgUser(id=telegram_id, is_bot=False, first_name="Sinov"),
            text=text,
        ),
    )


def callback_update(data: str, telegram_id: int) -> Update:
    return Update(
        update_id=next_id(),
        callback_query=CallbackQuery(
            id=str(next_id()),
            from_user=TgUser(id=telegram_id, is_bot=False, first_name="Sinov"),
            chat_instance="test",
            data=data,
            message=Message(
                message_id=next_id(),
                date=datetime.now(),
                chat=Chat(id=telegram_id, type="private"),
                text="eski xabar",
            ),
        ),
    )


# ======================================================================
#  SINOVLAR
# ======================================================================

async def main() -> int:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    print("\n--- Tayyorgarlik ---")
    async with session_factory() as session:
        users = UserRepository(session)

        admin, _ = await users.get_or_create(ADMIN_ID, first_name="Admin")
        admin.role = Role.ADMIN.value
        admin.is_registered = True

        student, _ = await users.get_or_create(STUDENT_ID, first_name="Oquvchi")
        student.role = Role.STUDENT.value
        student.is_registered = True

        await session.commit()
        print("  OK   admin va o'quvchi yaratildi")

    bot = make_bot()
    dispatcher = make_dispatcher()

    async def feed(update: Update) -> Any:
        return await dispatcher.feed_update(bot, update)

    # ------------------------------------------------------------------
    print("\n--- Tugmalar handler'ga yetib boradimi ---")

    result = await feed(callback_update(AdminCB(action="panel").pack(), ADMIN_ID))
    check("admin: 🛠 Admin panel", result is not UNHANDLED, True)

    result = await feed(callback_update(AdminCB(action="users", page=1).pack(), ADMIN_ID))
    check("admin: 👥 Foydalanuvchilar", result is not UNHANDLED, True)

    result = await feed(
        callback_update(AdminCB(action="solvers", page=1, period=7).pack(), ADMIN_ID)
    )
    check("admin: ✍️ Test yechganlar", result is not UNHANDLED, True)

    result = await feed(callback_update(AdminCB(action="board").pack(), ADMIN_ID))
    check("admin: 🏆 Reytinglar", result is not UNHANDLED, True)

    result = await feed(callback_update(MenuCB(action="create").pack(), ADMIN_ID))
    check("o'qituvchi: ➕ Test yaratish", result is not UNHANDLED, True)

    result = await feed(callback_update(MenuCB(action="mytests").pack(), ADMIN_ID))
    check("o'qituvchi: 📚 Mening testlarim", result is not UNHANDLED, True)

    result = await feed(callback_update(MenuCB(action="results").pack(), STUDENT_ID))
    check("o'quvchi: 📊 Natijalarim", result is not UNHANDLED, True)

    result = await feed(callback_update(MenuCB(action="board").pack(), STUDENT_ID))
    check("o'quvchi: 🏆 Reyting", result is not UNHANDLED, True)

    result = await feed(callback_update(MenuCB(action="profile").pack(), STUDENT_ID))
    check("o'quvchi: 👤 Profil", result is not UNHANDLED, True)

    result = await feed(callback_update(MenuCB(action="main").pack(), STUDENT_ID))
    check("🏠 Bosh menyu", result is not UNHANDLED, True)

    # ------------------------------------------------------------------
    print("\n--- Xabarlar handler'ga yetib boradimi ---")

    result = await feed(message_update("/start", STUDENT_ID))
    check("/start", result is not UNHANDLED, True)

    result = await feed(message_update("/admin", ADMIN_ID))
    check("/admin", result is not UNHANDLED, True)

    result = await feed(message_update("1", STUDENT_ID))
    check("test raqami «1»", result is not UNHANDLED, True)

    result = await feed(message_update("1*abcdabcd", STUDENT_ID))
    check("bir zumda «1*abcdabcd»", result is not UNHANDLED, True)

    result = await feed(message_update("Matematika+abcdabcd", ADMIN_ID))
    check("bitta xabarda test yaratish", result is not UNHANDLED, True)

    # ------------------------------------------------------------------
    print("\n--- Huquqsizlar chetlab o'tiladi ---")

    #  O'quvchi admin tugmasini bosolmaydi — router filtri to'sadi
    result = await feed(callback_update(AdminCB(action="panel").pack(), STUDENT_ID))
    check("o'quvchi admin panelga kira olmaydi", result is UNHANDLED, True)

    result = await feed(message_update("/admin", STUDENT_ID))
    check("o'quvchi /admin ishlatmaydi", result is UNHANDLED, True)

    result = await feed(message_update("Matematika+abcdabcd", STUDENT_ID))
    check("o'quvchi bir qatorli test yarata olmaydi", result is UNHANDLED, True)

    # ------------------------------------------------------------------
    print("\n--- Huquqi yo'qlarga chiroyli javob ---")

    #  MUHIM: bu update'lar `fallback` ga TUSHMASLIGI kerak.
    #  Ilgari "🤔 Tushunmadim" chiqardi — foydasiz javob edi.
    result = await feed(callback_update(MenuCB(action="create").pack(), STUDENT_ID))
    check("«Test yaratish» tushuntirish beradi", result is not UNHANDLED, True)

    result = await feed(message_update("/new", STUDENT_ID))
    check("/new tushuntirish beradi", result is not UNHANDLED, True)

    result = await feed(callback_update(MenuCB(action="mytests").pack(), STUDENT_ID))
    check("«Mening testlarim» tushuntirish beradi", result is not UNHANDLED, True)

    #  So'rov yuborish ishlaydimi
    result = await feed(
        callback_update(MenuCB(action="request_teacher").pack(), STUDENT_ID)
    )
    check("ruxsat so'rovi yuboriladi", result is not UNHANDLED, True)

    #  Admin so'rov haqida xabar oldimi
    check(
        "adminga xabar yuborildi",
        any(call.startswith("SendMessage") for call in bot.session.calls),
        True,
    )

    #  O'qituvchi esa haqiqiy handler'ga tushadi, tushuntirishga emas
    result = await feed(callback_update(MenuCB(action="create").pack(), ADMIN_ID))
    check("admin haqiqiy yaratish oqimiga tushadi", result is not UNHANDLED, True)

    # ------------------------------------------------------------------
    print("\n--- Deep link (poster tugmasi va QR kod) ---")

    #  Avval test yaratamiz
    async with session_factory() as session:
        from modules.catalog.service import CatalogService

        teacher = await UserRepository(session).get_by_telegram_id(ADMIN_ID)
        created = await CatalogService(session).create_from_one_line(
            teacher, "Deep link testi+abcdabcd"
        )
        test_number = created.number
        await session.commit()

    bot.session.calls.clear()

    result = await feed(message_update(f"/start t{test_number}", STUDENT_ID))
    check("havola orqali test ochildi", result is not UNHANDLED, True)
    check_true(
        "test kartochkasi yuborildi",
        any(call.startswith("SendMessage") for call in bot.session.calls),
    )

    result = await feed(message_update("/start t999999", STUDENT_ID))
    check("yo'q test — xato bermaydi", result is not UNHANDLED, True)

    result = await feed(message_update("/start cert_TL-2026-YOQXXX", STUDENT_ID))
    check("yo'q sertifikat — xato bermaydi", result is not UNHANDLED, True)

    result = await feed(message_update("/start", STUDENT_ID))
    check("oddiy /start ham ishlaydi", result is not UNHANDLED, True)

    # ------------------------------------------------------------------
    print("\n--- O'qituvchiga bildirishnoma ---")

    #  O'quvchi javob beradi -> muallifga xabar borishi kerak
    bot.session.calls.clear()

    result = await feed(
        message_update(f"{test_number}*abcdabcd", STUDENT_ID)
    )
    check("javob qabul qilindi", result is not UNHANDLED, True)

    #  Kamida ikkita xabar: o'quvchiga natija + muallifga bildirishnoma
    sends = [call for call in bot.session.calls if call.startswith(("SendMessage", "SendPhoto"))]
    check_true(f"xabarlar yuborildi ({len(sends)} ta)", len(sends) >= 2)

    # ------------------------------------------------------------------
    print("\n--- Middleware turi to'g'rimi ---")

    #  Aynan shu xato bo'lgan edi: filtrlar `user` ni ko'rishi uchun
    #  middleware TASHQI (outer) bo'lishi shart
    outer = len(dispatcher.message.outer_middleware._middlewares)
    inner = len(dispatcher.message.middleware._middlewares)
    #  logging, throttling, database, user, subscription
    check("5 ta tashqi middleware", outer, 5)
    check("ichki middleware yo'q", inner, 0)

    # ------------------------------------------------------------------
    print("\n--- Bloklangan foydalanuvchi to'xtatiladi ---")

    async with session_factory() as session:
        users = UserRepository(session)
        blocked = await users.get_by_telegram_id(STUDENT_ID)
        await users.ban(blocked, reason="sinov")
        await session.commit()

    result = await feed(message_update("/start", STUDENT_ID))
    check("bloklangan o'tolmaydi", result is None, True)

    async with session_factory() as session:
        users = UserRepository(session)
        blocked = await users.get_by_telegram_id(STUDENT_ID)
        await users.unban(blocked)
        await session.commit()

    await bot.session.close()
    await engine.dispose()

    print()
    if _failures:
        print(f"  {len(_failures)} ta sinov muvaffaqiyatsiz:")
        for name in _failures:
            print(f"    - {name}")
        return 1

    print("  MARSHRUTLASH TO'G'RI")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
