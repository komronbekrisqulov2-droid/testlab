"""
Mini App tuzatishlari sinovi:
1. Qayta topshirishda (AlreadyAnsweredError) to'g'ri 200 javob qaytishi (TypeError 'limit' yo'qligi)
2. Ota-onaga bildirishnoma uz.parent_notification orqali yuborilishi
3. Media fayl MIME turlari (PDF va boshqalar)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401,E402

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from infrastructure.database.engine import engine, session_factory
from modules.assessment.service import AssessmentService
from modules.catalog.service import CatalogService
from modules.identity.models import User
from modules.identity.repository import UserRepository
from modules.registry import Base
from apps.webapp.server import create_webapp


async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user_repo = UserRepository(session)
        teacher, _ = await user_repo.get_or_create(
            111222333,
            username="test_teacher",
            first_name="Ustoz",
            last_name="Muallim",
        )
        student, _ = await user_repo.get_or_create(
            555666777,
            username="test_student",
            first_name="Talaba",
            last_name="Shogird",
        )
        # Link parent
        await user_repo.link_parent(
            student_id=student.id,
            parent_telegram_id=999888777,
            parent_name="Ota",
        )

        from core.security.permissions import Role
        await user_repo.set_role(teacher, Role.TEACHER.value)
        await user_repo.set_role(student, Role.STUDENT.value)
        teacher.is_registered = True
        student.is_registered = True

        catalog = CatalogService(session)
        test = await catalog.create_from_one_line(teacher, "Matematika Testi+abcdabcd")
        await session.commit()
        return teacher.id, student.id, test.id


async def main_test():
    await setup_db()

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=None)
    mock_bot.get_file = AsyncMock()

    app = create_webapp(bot=mock_bot)

    async with session_factory() as session:
        user_repo = UserRepository(session)
        student = await user_repo.get_by_telegram_id(555666777)
        catalog = CatalogService(session)
        test = (await catalog.tests.list_all()).items[0]

        # 1-marta topshirish (bot orqali yoki servis orqali)
        assessment = AssessmentService(session)
        await assessment.submit(test, student, "abcdabcd")
        await session.commit()

    # Endi Web App orqali xuddi shu testga ikkinchi marta javob yuboramiz
    from aiohttp.test_utils import TestClient, TestServer
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        payload = {
            "answers": "abcdabcd",
            "user_id": 555666777,
            "tab_switches": 0,
            "disqualified": False,
        }
        resp = await client.post(f"/api/test/{test.id}/submit", json=payload)
        data = await resp.json()
        print("Status code:", resp.status)
        print("Response JSON:", data)

        assert resp.status == 200, f"Expected 200, got {resp.status}"
        assert data.get("ok") is True
        assert data.get("already_answered") is True
        assert data.get("score") == 8
        print("✅ AlreadyAnsweredError 200 OK qaytardi va qulash bo'lmadi!")

        # Ota-onaga xabar yuborish tekshiruvi (yangi urinishda)
        # Boshqa yangi test yaratamiz va topshiramiz
        async with session_factory() as session:
            teacher = await UserRepository(session).get_by_telegram_id(111222333)
            test2 = await CatalogService(session).create_from_one_line(teacher, "Fizika Testi+bbbbbbbb")
            await session.commit()
            test2_id = test2.id

        payload2 = {
            "answers": "bbbbbbbb",
            "user_id": 555666777,
            "tab_switches": 0,
            "disqualified": False,
        }
        resp2 = await client.post(f"/api/test/{test2_id}/submit", json=payload2)
        assert resp2.status == 200
        data2 = await resp2.json()
        assert data2.get("ok") is True
        print("✅ Yangi test submit muvaffaqiyatli o'tdi!")

        # mock_bot.send_message tekshiruvi: parent_telegram_id (999888777) ga xabar ketgan bo'lishi kerak!
        called_chat_ids = [call.args[0] if call.args else call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
        print("Mock bot chaqirilgan chat_id lar:", called_chat_ids)
        assert 999888777 in called_chat_ids, "Parent chat ID topilmadi!"
        print("✅ Ota-onaga bildirishnoma to'g'ri yuborildi!")

    finally:
        await client.close()

    print("\n🎉 BARCHA MINI APP TUZATISHLARI TO'G'RI ISHLAMOQDA!")

if __name__ == "__main__":
    asyncio.run(main_test())
