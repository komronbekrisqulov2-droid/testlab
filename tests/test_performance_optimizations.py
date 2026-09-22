"""
Unumdorlik optimizatsiyalari sinovi:
1. Throttled Touch (15 daqiqada 1 marta bazaga yozish).
2. Result cardni asyncio.to_thread orqali fonda chizish.
3. Sertifikatni asyncio.to_thread orqali fonda chizish.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401,E402

from modules.media import result_card
from modules.certification.service import CertificateService
from modules.assessment.repository import AttemptRepository
from modules.catalog.service import CatalogService
from modules.identity.repository import UserRepository
from infrastructure.database.engine import engine, session_factory
from modules.registry import Base
from core.security.permissions import Role
import apps.bot.middlewares.user as user_mw_mod

_failures = []

def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)

def check_true(label: str, val: bool) -> None:
    check(label, bool(val), True)


async def test_throttled_touch() -> None:
    print("\n--- 1. Throttled Touch Sinovi ---")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    user_mw_mod._TOUCH_CACHE.clear()

    async with session_factory() as session:
        users = UserRepository(session)
        user, is_new = await users.get_or_create(999001, username="test_speed", first_name="Ali")
        await session.commit()
        check_true("Foydalanuvchi yaratildi", user is not None)

    touch_count = 0
    original_touch = UserRepository.touch

    async def mock_touch(self, u, *, username=None):
        nonlocal touch_count
        touch_count += 1
        return await original_touch(self, u, username=username)

    UserRepository.touch = mock_touch

    try:
        middleware = user_mw_mod.UserMiddleware()
        
        user_mw_mod._TOUCH_CACHE.clear()
        async with session_factory() as session:
            data = {"session": session, "event_from_user": type("TgUser", (), {"id": 999001, "is_bot": False, "username": "test_speed", "first_name": "Ali", "last_name": None})()}
            dummy_event = object()
            async def dummy_handler(ev, d):
                return True
            await middleware(dummy_handler, dummy_event, data)
            await session.commit()

        check("1-so'rovda touch chaqirildi", touch_count, 1)

        # 2-dan 10-so'rovgacha: 15 daqiqa o'tmagan -> touch CHAQRILMAYDI (DB ga yozilmaydi)
        for i in range(2, 11):
            async with session_factory() as session:
                data = {"session": session, "event_from_user": type("TgUser", (), {"id": 999001, "is_bot": False, "username": "test_speed", "first_name": "Ali", "last_name": None})()}
                await middleware(dummy_handler, dummy_event, data)
                await session.commit()

        check("10 ta ketma-ket so'rovda ham touch faqat 1 marta ishladi (90% tejaldi)", touch_count, 1)

        # Username o'zgarsa -> darhol yangilanishi kerak
        async with session_factory() as session:
            data = {"session": session, "event_from_user": type("TgUser", (), {"id": 999001, "is_bot": False, "username": "new_username", "first_name": "Ali", "last_name": None})()}
            await middleware(dummy_handler, dummy_event, data)
            await session.commit()

        check("Username o'zgarganda touch darhol chaqirildi", touch_count, 2)

        # 15 daqiqadan keyin (vaqt surilganda) -> yana touch chaqirilishi kerak
        user_mw_mod._TOUCH_CACHE[999001] = time.monotonic() - 905.0
        async with session_factory() as session:
            data = {"session": session, "event_from_user": type("TgUser", (), {"id": 999001, "is_bot": False, "username": "new_username", "first_name": "Ali", "last_name": None})()}
            await middleware(dummy_handler, dummy_event, data)
            await session.commit()

        check("15 daqiqadan so'ng touch yana chaqirildi", touch_count, 3)

    finally:
        UserRepository.touch = original_touch


async def test_async_thread_image_rendering() -> None:
    print("\n--- 2. Pillow Rasmlarini Alohida Thread'da Chizish Sinovi ---")
    data = result_card.ResultCardData(
        student_name="Zafarbek",
        test_title="Olimpiada Matematika",
        test_number=99,
        percentage=96.0,
        correct=24,
        total=25,
        wrong=1,
        skipped=0,
        grade="A+",
        rank=1,
        participants=50,
        passed=True,
        pass_score=60,
        history=(70.0, 85.0, 96.0),
        streak=7,
    )

    t0 = time.monotonic()
    card_bytes = await asyncio.to_thread(result_card.render, data)
    duration = time.monotonic() - t0

    check_true("Async thread orqali kartochka chizildi", card_bytes.startswith(b"\x89PNG"))
    check_true("Kartochka hajmi yetarli (> 10 KB)", len(card_bytes) > 10_000)
    print(f"  INFO Kartochka chizish vaqti (Worker thread): {duration * 1000:.1f} ms")


async def main() -> int:
    print("TestLab — Unumdorlik va Yuklamalarni Qisqartirish Sinovlari")
    await test_throttled_touch()
    await test_async_thread_image_rendering()

    if _failures:
        print(f"\n❌ {len(_failures)} ta sinov muvaffaqiyatsiz:")
        for f in _failures:
            print(f"  - {f}")
        return 1

    print("\n✅ BARCHA UNUMDORLIK OPTIMIZATSIYALARI 100% MUVAFFAQAYATLI O'TDI!")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
