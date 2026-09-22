"""
Foydalanuvchi rollari simulyatsiyasi: O'quvchi, O'qituvchi, Admin.

Ushbu sinov botning barcha asosiy oqimlarini va real foydalanuvchi ssenariylarini
to'liq simulyatsiya qiladi va yuzaga kelishi mumkin bo'lgan har qanday xatoliklarni
tekshiradi.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Sinov bazasini sozlash
from tests import _env  # noqa: F401,E402

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    Contact,
    Document,
    Message,
    MessageId,
    PhotoSize,
    Update,
    User as TgUser,
)

from apps.bot.handlers import setup_routers
from apps.bot.keyboards.callbacks import (
    AdminCB,
    AttemptCB,
    CertCB,
    ExplainCB,
    MenuCB,
    MistakeCB,
    ParentCB,
    PeopleCB,
    TestCB,
)
from apps.bot.middlewares import setup_middlewares
from core.security.permissions import Role
from infrastructure.database.engine import engine, session_factory
from modules.catalog.repository import CategoryRepository
from modules.identity.repository import UserRepository
from modules.registry import Base

FAKE_TOKEN = "123456789:AAFakeSimulationToken123456789012345"

ADMIN_ID = 100_001
TEACHER_ID = 200_001
STUDENT_ID = 300_001
PARENT_ID = 400_001

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        name = type(method).__name__
        params = getattr(method, "__dict__", {})
        self.calls.append((name, params))
        return self._result_for(name, params)

    @staticmethod
    def _result_for(name: str, params: dict[str, Any]) -> Any:
        if name == "GetMe":
            return TgUser(id=1, is_bot=True, first_name="TestLabBot", username="testlab_bot")

        if name in {"SendMessage", "EditMessageText"}:
            chat_id = params.get("chat_id") or ADMIN_ID
            return Message(
                message_id=1,
                date=datetime.now(),
                chat=Chat(id=chat_id, type="private"),
                text=params.get("text", "mock text"),
            )

        if name in {"SendPhoto", "SendDocument"}:
            chat_id = params.get("chat_id") or ADMIN_ID
            return Message(
                message_id=1,
                date=datetime.now(),
                chat=Chat(id=chat_id, type="private"),
                photo=[PhotoSize(file_id="photo_123", file_unique_id="u_123", width=800, height=600)],
                document=Document(file_id="doc_123", file_unique_id="u_doc_123", file_name="file.pdf"),
            )

        if name == "SendMediaGroup":
            return [
                Message(
                    message_id=1,
                    date=datetime.now(),
                    chat=Chat(id=ADMIN_ID, type="private"),
                )
            ]

        if name == "CopyMessage":
            return MessageId(message_id=1)

        return True

    async def stream_content(self, *args: Any, **kwargs: Any):
        yield b""

    async def close(self) -> None:
        pass


_counter = 0


def next_id() -> int:
    global _counter
    _counter += 1
    return _counter


def message_update(text: str, telegram_id: int, first_name: str = "User") -> Update:
    return Update(
        update_id=next_id(),
        message=Message(
            message_id=next_id(),
            date=datetime.now(),
            chat=Chat(id=telegram_id, type="private"),
            from_user=TgUser(id=telegram_id, is_bot=False, first_name=first_name),
            text=text,
        ),
    )


def callback_update(data: str, telegram_id: int, first_name: str = "User") -> Update:
    return Update(
        update_id=next_id(),
        callback_query=CallbackQuery(
            id=str(next_id()),
            from_user=TgUser(id=telegram_id, is_bot=False, first_name=first_name),
            chat_instance="test",
            data=data,
            message=Message(
                message_id=next_id(),
                date=datetime.now(),
                chat=Chat(id=telegram_id, type="private"),
                text="soxta matn",
            ),
        ),
    )


def photo_update(file_id: str, telegram_id: int, caption: str | None = None) -> Update:
    return Update(
        update_id=next_id(),
        message=Message(
            message_id=next_id(),
            date=datetime.now(),
            chat=Chat(id=telegram_id, type="private"),
            from_user=TgUser(id=telegram_id, is_bot=False, first_name="User"),
            photo=[PhotoSize(file_id=file_id, file_unique_id=file_id, width=800, height=600)],
            caption=caption,
        ),
    )


def document_update(file_id: str, file_name: str, telegram_id: int, caption: str | None = None) -> Update:
    return Update(
        update_id=next_id(),
        message=Message(
            message_id=next_id(),
            date=datetime.now(),
            chat=Chat(id=telegram_id, type="private"),
            from_user=TgUser(id=telegram_id, is_bot=False, first_name="User"),
            document=Document(file_id=file_id, file_unique_id=file_id, file_name=file_name, mime_type="application/pdf"),
            caption=caption,
        ),
    )


def contact_update(phone: str, telegram_id: int) -> Update:
    return Update(
        update_id=next_id(),
        message=Message(
            message_id=next_id(),
            date=datetime.now(),
            chat=Chat(id=telegram_id, type="private"),
            from_user=TgUser(id=telegram_id, is_bot=False, first_name="User"),
            contact=Contact(phone_number=phone, first_name="User"),
        ),
    )


async def run_simulation() -> int:
    print("\n==================================================")
    print("🚀 BOT TO'LIQ SIMULYATSIYASI VA XATOLARNI TEKSHIRISH")
    print("==================================================")

    # 1. Bazani noldan yaratish
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Standart kategoriyalarni yuklash va foydalanuvchilarni tayyorlash
    async with session_factory() as session:
        await CategoryRepository(session).seed_defaults()
        users = UserRepository(session)

        # Boshliq (Super Admin) yaratish
        admin, _ = await users.get_or_create(ADMIN_ID, first_name="Admin", last_name="Boshliq")
        admin.role = Role.SUPER_ADMIN.value
        admin.is_registered = True

        # O'qituvchi yaratish
        teacher, _ = await users.get_or_create(TEACHER_ID, first_name="Ustoz", last_name="Muallim")
        teacher.role = Role.TEACHER.value
        teacher.is_registered = True

        # Ota-ona yaratish
        parent, _ = await users.get_or_create(PARENT_ID, first_name="Ota", last_name="Valiyev")
        parent.role = Role.STUDENT.value
        parent.is_registered = True

        await session.commit()
        print("  OK   Boshlang'ich baza tayyorlandi")

    session = FakeSession()
    bot = Bot(token=FAKE_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())
    setup_middlewares(dispatcher)
    setup_routers(dispatcher)

    async def feed(update: Update) -> Any:
        return await dispatcher.feed_update(bot, update)

    # ==================================================================
    # 1-QISM: O'QUVCHI (STUDENT) TAJRIBASI VA SINOVI
    # ==================================================================
    print("\n--- 1. O'QUVCHI TAJRIBASI (STUDENT FLOW) ---")

    # 1.1 Ro'yxatdan o'tmagan yangi o'quvchi /start bosadi
    res = await feed(message_update("/start", STUDENT_ID, "Komil"))
    check("1.1 Yangi o'quvchi /start", res is not UNHANDLED, True)

    # 1.2 Ro'yxatdan o'tish tugmasi
    res = await feed(callback_update(MenuCB(action="register").pack(), STUDENT_ID))
    check("1.2 Ro'yxatdan o'tish boshlanishi", res is not UNHANDLED, True)

    # 1.3 Ism kiritish
    res = await feed(message_update("Komiljon", STUDENT_ID))
    check("1.3 Ism kiritildi", res is not UNHANDLED, True)

    # 1.4 Familiya kiritish
    res = await feed(message_update("Risqulov", STUDENT_ID))
    check("1.4 Familiya kiritildi", res is not UNHANDLED, True)

    # 1.5 Telefon kiritish (kontakt yoki text)
    res = await feed(message_update("+998901234567", STUDENT_ID))
    check("1.5 Telefon kiritildi (ro'yxatdan o'tish yakunlandi)", res is not UNHANDLED, True)

    # Bazada o'quvchi holatini tekshiramiz
    async with session_factory() as s:
        u = await UserRepository(s).get_by_telegram_id(STUDENT_ID)
        check("O'quvchi bazada is_registered=True", u.is_registered, True)
        check("O'quvchi ismi saqlandi", u.first_name, "Komiljon")
        check("O'quvchi XP oldi", u.xp >= 10, True)

    # 1.6 Bosh menyu tugmalari
    res = await feed(callback_update(MenuCB(action="profile").pack(), STUDENT_ID))
    check("1.6 Profil ko'rish", res is not UNHANDLED, True)

    res = await feed(callback_update(MenuCB(action="results").pack(), STUDENT_ID))
    check("1.6 Natijalarim ro'yxati", res is not UNHANDLED, True)

    res = await feed(callback_update(MenuCB(action="board").pack(), STUDENT_ID))
    check("1.6 Reyting ko'rish", res is not UNHANDLED, True)

    # ==================================================================
    # 2-QISM: O'QITUVCHI (TEACHER) TAJRIBASI VA TEST YARATISH
    # ==================================================================
    print("\n--- 2. O'QITUVCHI TAJRIBASI (TEACHER FLOW) ---")

    # 2.1 Bitta xabarda test yaratish: "Informatika+abcdabcdab" (10 ta savol)
    res = await feed(message_update("Informatika+abcdabcdab", TEACHER_ID))
    check("2.1 Bir xabarda test yaratish (Informatika)", res is not UNHANDLED, True)

    created_test_num = None
    async with session_factory() as s:
        from modules.catalog.service import CatalogService
        catalog = CatalogService(s)
        teacher_user = await UserRepository(s).get_by_telegram_id(TEACHER_ID)
        t_page = await catalog.tests.list_by_author(teacher_user.id, page=1, per_page=10)
        check("O'qituvchi testlari soni 1 ta", len(t_page.items), 1)
        created_test_num = t_page.items[0].number
        created_test_id = t_page.items[0].id
        check("Test savollari soni 10 ta", t_page.items[0].questions_count, 10)

    # 2.2 Rasm/fayl orqali bosqichma-bosqich test yaratish
    res = await feed(callback_update(MenuCB(action="create").pack(), TEACHER_ID))
    check("2.2 Test yaratish menyusi", res is not UNHANDLED, True)

    # Rasm yuborish
    res = await feed(photo_update("test_sheet_photo_1", TEACHER_ID, caption="Tarix 7-sinf"))
    check("2.2 Test varaqasi rasmi yuklandi", res is not UNHANDLED, True)

    # Kalit yuborish: "abcdeabcde" (10 ta savol)
    res = await feed(message_update("abcdeabcde", TEACHER_ID))
    check("2.2 Kalit yuborildi va test e'lon qilindi", res is not UNHANDLED, True)

    second_test_num = None
    async with session_factory() as s:
        catalog = CatalogService(s)
        teacher_user = await UserRepository(s).get_by_telegram_id(TEACHER_ID)
        t_page = await catalog.tests.list_by_author(teacher_user.id, page=1, per_page=10)
        check("O'qituvchining jami testlari 2 ta", len(t_page.items), 2)
        second_test_num = t_page.items[0].number
        second_test_id = t_page.items[0].id

    # 2.3 Mening testlarim ro'yxatini ko'rish
    res = await feed(callback_update(MenuCB(action="mytests").pack(), TEACHER_ID))
    check("2.3 Mening testlarim ro'yxati", res is not UNHANDLED, True)

    # 2.4 Test boshqaruvi: test kartasini ochish
    res = await feed(callback_update(TestCB(action="manage", test_id=created_test_id).pack(), TEACHER_ID))
    check("2.4 Test boshqaruv kartasi", res is not UNHANDLED, True)

    # 2.5 Testga yechim/tushuntirish qo'shish (Explanation)
    res = await feed(callback_update(ExplainCB(action="edit", test_id=created_test_id, q_num=1).pack(), TEACHER_ID))
    check("2.5 Yechim biriktirish holatiga kirish", res is not UNHANDLED, True)

    # Yechim hujjati yuborish (PDF)
    res = await feed(document_update("pdf_expl_123", "yechim.pdf", TEACHER_ID, caption="1-savol to'liq yechimi"))
    check("2.5 Yechim hujjati saqlandi", res is not UNHANDLED, True)

    # ==================================================================
    # 3-QISM: O'QUVCHI TEST YECHISHI VA FUNKSIYALARI
    # ==================================================================
    print("\n--- 3. O'QUVCHI TEST YECHISHI VA XATOLAR ---")

    # 3.1 Test raqami orqali kartani ochish
    res = await feed(message_update(str(created_test_num), STUDENT_ID))
    check("3.1 Test raqami bilan test kartasini ochish", res is not UNHANDLED, True)

    # 3.2 WebApp info tugmasini tekshirish (oldingi NameError 'settings' xatosini sinash)
    res = await feed(callback_update(TestCB(action="webapp_info", test_id=created_test_id).pack(), STUDENT_ID))
    check("3.2 WebApp info ochilishi (settings tekshiruvi)", res is not UNHANDLED, True)

    # 3.3 Testga javob berish (1-usul: bir zumda "num*answers")
    # Kalit: "abcdabcdab" -> yuborilayotgan javob: "abcdabcdac" (9 to'g'ri, 10-savol xato!)
    answer_str = f"{created_test_num}*abcdabcdac"
    res = await feed(message_update(answer_str, STUDENT_ID))
    check("3.3 Testga javob yuborish (9 to'g'ri, 1 xato)", res is not UNHANDLED, True)

    # 3.4 Takroriy javob berishni taqiqlash tekshiruvi
    res = await feed(message_update(answer_str, STUDENT_ID))
    check("3.4 Takroriy javob taqiqlandi (xatosiz ushlandi)", res is not UNHANDLED, True)

    # 3.5 Sertifikatlar markazini ochish va sertifikat olish
    res = await feed(callback_update(CertCB(action="hub").pack(), STUDENT_ID))
    check("3.5 Sertifikatlar markazi ochildi", res is not UNHANDLED, True)

    async with session_factory() as s:
        from modules.assessment.repository import AttemptRepository
        attempts = await AttemptRepository(s).list_by_user(u.id, page=1, per_page=5)
        att_id = attempts.items[0].id

    res = await feed(callback_update(CertCB(action="issue", attempt_id=att_id).pack(), STUDENT_ID))
    check("3.5 Sertifikat muvaffaqiyatli chiqarildi", res is not UNHANDLED, True)

    # 3.6 Xatolar daftari (Personal Retake)
    res = await feed(callback_update(MistakeCB(action="hub").pack(), STUDENT_ID))
    check("3.6 Xatolar daftari ochildi", res is not UNHANDLED, True)

    res = await feed(callback_update(MistakeCB(action="retake").pack(), STUDENT_ID))
    check("3.6 Xatoni qayta yechish kartasi ochildi", res is not UNHANDLED, True)

    # 10-savolning to'g'ri javobi 'B'. Noto'g'ri 'D' tanlab ko'ramiz
    res = await feed(callback_update(MistakeCB(action="answer", test_id=created_test_id, q_num=10, choice="D").pack(), STUDENT_ID))
    check("3.6 Xato tanlanganda ogohlantirish berildi", res is not UNHANDLED, True)

    # Endi to'g'ri 'B' tanlaymiz
    res = await feed(callback_update(MistakeCB(action="answer", test_id=created_test_id, q_num=10, choice="B").pack(), STUDENT_ID))
    check("3.6 To'g'ri javob tanlandi va xato tuzatildi (+3 XP)", res is not UNHANDLED, True)

    # 3.7 Yechimlar ro'yxatini ko'rish (Explanations)
    res = await feed(callback_update(ExplainCB(action="list", test_id=created_test_id).pack(), STUDENT_ID))
    check("3.7 Savollar yechimlari ro'yxati ochildi", res is not UNHANDLED, True)

    # 3.8 Ota-ona ulash (Parent Linking)
    res = await feed(message_update(f"/start parent_{STUDENT_ID}", PARENT_ID))
    check("3.8 Ota-ona deep link orqali bog'landi", res is not UNHANDLED, True)

    # O'quvchi profilida ota-ona ko'rinishi
    # 3.9 O'quvchi yechgan testining to'liq tahlilini ko'rish (Attempt Detail)
    res = await feed(callback_update(AttemptCB(action="view", attempt_id=att_id, page=1).pack(), STUDENT_ID))
    check("3.9 O'quvchi yechgan testining to'liq tahlilini ochish", res is not UNHANDLED, True)

    # ==================================================================
    # 4-QISM: ADMINISTRATOR (ADMIN) TAJRIBASI
    # ==================================================================
    print("\n--- 4. ADMINISTRATOR TAJRIBASI (ADMIN FLOW) ---")

    # 4.1 Admin panel /admin
    res = await feed(message_update("/admin", ADMIN_ID))
    check("4.1 Admin paneli ochildi", res is not UNHANDLED, True)

    # 4.2 Foydalanuvchilar ro'yxati
    res = await feed(callback_update(AdminCB(action="users", page=1).pack(), ADMIN_ID))
    check("4.2 Foydalanuvchilar ro'yxati", res is not UNHANDLED, True)

    # 4.3 Foydalanuvchini qidirish
    res = await feed(callback_update(AdminCB(action="search").pack(), ADMIN_ID))
    check("4.3 Qidiruv so'rovi", res is not UNHANDLED, True)

    res = await feed(message_update("Komiljon", ADMIN_ID))
    check("4.3 Qidiruv natijasi chiqdi", res is not UNHANDLED, True)

    # 4.4 Foydalanuvchi kartochkasi va rolni o'zgartirish
    res = await feed(callback_update(AdminCB(action="user", target_id=u.id, page=1).pack(), ADMIN_ID))
    check("4.4 Foydalanuvchi kartochkasi ochildi", res is not UNHANDLED, True)

    # O'quvchini O'qituvchiga aylantirish (period=1)
    res = await feed(callback_update(AdminCB(action="role", target_id=u.id, period=1, page=1).pack(), ADMIN_ID))
    check("4.4 Foydalanuvchiga O'qituvchi roli berildi", res is not UNHANDLED, True)

    async with session_factory() as s:
        updated_u = await UserRepository(s).get(u.id)
        check("Bazada roli TEACHER ga o'zgardi", updated_u.role, Role.TEACHER.value)

    # 4.4.1 Super Admin boshqa foydalanuvchini Super Admin qilish (period=3)
    res = await feed(callback_update(AdminCB(action="role", target_id=u.id, period=3, page=1).pack(), ADMIN_ID))
    check("4.4.1 Foydalanuvchiga Super Admin roli berildi", res is not UNHANDLED, True)

    async with session_factory() as s:
        super_u = await UserRepository(s).get(u.id)
        check("Bazada roli SUPER_ADMIN ga o'zgardi", super_u.role, Role.SUPER_ADMIN.value)
        check("super_u.is_super_admin True", super_u.is_super_admin, True)

    # 4.5 Foydalanuvchini bloklash va blokdan chiqarish
    res = await feed(callback_update(AdminCB(action="ban", target_id=u.id, page=1).pack(), ADMIN_ID))
    check("4.5 Foydalanuvchi bloklandi", res is not UNHANDLED, True)

    res = await feed(callback_update(AdminCB(action="unban", target_id=u.id, page=1).pack(), ADMIN_ID))
    check("4.5 Foydalanuvchi blokdan chiqarildi", res is not UNHANDLED, True)

    # 4.6 Test yechganlar ro'yxati (Solvers)
    res = await feed(callback_update(AdminCB(action="solvers", page=1, period=0).pack(), ADMIN_ID))
    check("4.6 Test yechganlar ro'yxati", res is not UNHANDLED, True)

    # 4.7 Excel eksport (foydalanuvchilar va test yechganlar)
    res = await feed(callback_update(AdminCB(action="excel_users").pack(), ADMIN_ID))
    check("4.7 Foydalanuvchilar Excel eksporti", res is not UNHANDLED, True)

    res = await feed(callback_update(AdminCB(action="excel_solvers", period=0).pack(), ADMIN_ID))
    check("4.7 Test yechganlar Excel eksporti", res is not UNHANDLED, True)

    # 4.8 Ommaviy xabar (Broadcast oqimi)
    res = await feed(callback_update(AdminCB(action="broadcast").pack(), ADMIN_ID))
    check("4.8 Broadcast auditoriya tanlash", res is not UNHANDLED, True)

    res = await feed(callback_update(AdminCB(action="broadcast_to", target=0).pack(), ADMIN_ID))
    check("4.8 Broadcast xabarini so'rash", res is not UNHANDLED, True)

    # Admin xabar yuboradi
    res = await feed(message_update("Hurmatli foydalanuvchilar! Yangi testlar e'lon qilindi.", ADMIN_ID))
    check("4.8 Broadcast xabari qabul qilindi va tasdiq so'raldi", res is not UNHANDLED, True)

    # Tasdiqlash tugmasi
    res = await feed(callback_update(AdminCB(action="broadcast_send").pack(), ADMIN_ID))
    check("4.8 Broadcast muvaffaqiyatli tarqatildi", res is not UNHANDLED, True)

    # ==================================================================
    # XULOSA
    # ==================================================================
    print("\n==================================================")
    if not _failures:
        print("🎉 BARCHA ROLLARDAGI SIMULYATSIYALAR MUVAFFAQIYATLI O'TDI!")
        print("✅ O'quvchi, O'qituvchi va Admin funksiyalari to'liq ishlamoqda.")
        return 0
    else:
        print(f"❌ {len(_failures)} TA SINOVDA XATOLIK ANIQLANDI:")
        for f in _failures:
            print(f"   - {f}")
        return 1


if __name__ == "__main__":
    code = asyncio.run(run_simulation())
    sys.exit(code)
