"""
Kanalga test ulashish va yakuniy natijalarni (Top-10 reyting) e'lon qilish sinovi.

Ishga tushirish:
    python tests/test_channel_post.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#  ⚠️ MUHIM: engine importidan OLDIN sinov bazasi
from tests import _env  # noqa: F401,E402

from apps.bot.tasks import apply_test_schedule  # noqa: E402
from apps.bot.texts import uz  # noqa: E402
from core.datetime_utils import utcnow  # noqa: E402
from infrastructure.database.engine import engine, session_factory  # noqa: E402
from modules.assessment.models import Attempt, AttemptStatus  # noqa: E402
from modules.assessment.service import AssessmentService  # noqa: E402
from modules.catalog.models import Test, TestStatus  # noqa: E402
from modules.catalog.service import CatalogService  # noqa: E402
from modules.identity.models import User  # noqa: E402
from modules.identity.repository import UserRepository  # noqa: E402
from modules.registry import Base  # noqa: E402

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}: kutilgan={want!r}, olingan={got!r}")
        _failures.append(label)


def check_true(label: str, condition: bool) -> None:
    if condition:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}: shart bajarilmadi")
        _failures.append(label)


async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def main():
    await setup_db()
    print("\n--- 1. Matn va formatlash sinovi ---")
    async with session_factory() as session:
        from modules.catalog.repository import CategoryRepository
        await CategoryRepository(session).seed_defaults()

        author = User(
            telegram_id=99901,
            role="teacher",
            first_name="Ustoz",
            is_registered=True,
        )
        session.add(author)
        await session.commit()
        await session.refresh(author)

        catalog = CatalogService(session)
        test = await catalog.create_from_one_line(author, "Matematika Quiz+abcdabcd")
        await catalog.tests.update_fields(

            test,
            time_limit_sec=1800,
            ends_at=utcnow() + timedelta(hours=2),
            channel_id=-1001234567890,
            channel_message_id=42,
        )
        await session.commit()
        await session.refresh(test)


        post_caption = uz.channel_test_post(test, "testlab_bot")
        check_true("Post matnida test nomi bor", "Matematika Quiz" in post_caption)
        check_true("Post matnida test kodi bor", str(test.number) in post_caption)
        check_true("Post matnida savollar soni bor", "8 ta" in post_caption)
        check_true("Post matnida taymer bor", "30 daqiqa" in post_caption)

        # Ishtirokchisiz reyting
        empty_leaderboard = uz.channel_leaderboard(test, [], 0)
        check_true("Bo'sh reyting xabari to'g'ri", "Testda hech kim qatnashmadi" in empty_leaderboard)

    print("\n--- 2. Top-10 reyting va medallar sinovi ---")
    async with session_factory() as session:
        users = []
        for i in range(1, 13):
            u = User(
                telegram_id=10000 + i,
                role="student",
                first_name=f"O'quvchi {i}",
                is_registered=True,
            )
            session.add(u)
            users.append(u)
        await session.commit()

        # 12 ta urinish qo'shamiz (har xil ball bilan)
        for i, u in enumerate(users, start=1):
            att = Attempt(
                test_id=test.id,
                user_id=u.id,
                status=AttemptStatus.FINISHED.value,
                score=i,
                max_score=12,
                percentage=round((i / 12) * 100, 1),
                correct_count=i,
                duration_sec=100 + i,
                finished_at=utcnow(),
            )
            session.add(att)
        await session.commit()

        # Top-10 reytingini olamiz
        from modules.assessment.repository import AttemptRepository
        repo = AttemptRepository(session)
        page = await repo.list_by_test(test.id, page=1, per_page=10, by_rank=True)
        total_cnt = await repo.count_finished_by_test(test.id)

        check("Jami ishtirokchilar 12 ta", total_cnt, 12)
        check("Birinchi sahifada 10 ta", len(page.items), 10)

        board_text = uz.channel_leaderboard(test, page.items, total_cnt)
        check_true("Top-1 da oltin medal bor", "🥇" in board_text)
        check_true("Top-2 da kumush medal bor", "🥈" in board_text)
        check_true("Top-3 da bronza medal bor", "🥉" in board_text)
        check_true("Jami ishtirokchilar soni ko'rsatilgan", "12 ta" in board_text)
        check_true("Eng yuqori ball olgan 1-o'rinda", "O&#x27;quvchi 12" in board_text or "O'quvchi 12" in board_text)

    print("\n--- 3. Fon vazifasi: Vaqti tugagan testni kanalga avtomatik e'lon qilish ---")
    async with session_factory() as session:
        catalog = CatalogService(session)
        t = await catalog.tests.get(test.id)
        t.ends_at = utcnow() - timedelta(minutes=5)
        await session.commit()




    # Bot mock
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())

    await apply_test_schedule(mock_bot)

    async with session_factory() as session:
        catalog = CatalogService(session)
        t = await catalog.tests.get(test.id)
        check("Test status arxivlandi", t.status, TestStatus.ARCHIVED.value)
        check_true("results_posted_at belgilandi", t.results_posted_at is not None)

    # mock_bot.send_message tekshiruvi
    # Kanalga xabar yuborilgan bo'lishi kerak
    channel_calls = [
        call for call in mock_bot.send_message.call_args_list
        if call.kwargs.get("chat_id") == -1001234567890
    ]
    check("Kanalga bitta xabar yuborildi", len(channel_calls), 1)
    call_kwargs = channel_calls[0].kwargs
    check_true("Kanal xabarida g'oliblar ro'yxati bor", "TOP-10 G'OLIBLAR RO'YXATI" in call_kwargs["text"])
    check("Asl xabarga reply qilingan", call_kwargs.get("reply_to_message_id"), 42)

    print("\n--- 4. Takroriy yurish dublikat xabar chiqarmaydi ---")
    mock_bot.send_message.reset_mock()
    await apply_test_schedule(mock_bot)
    channel_calls_repeat = [
        call for call in mock_bot.send_message.call_args_list
        if call.kwargs.get("chat_id") == -1001234567890
    ]
    check("Takroriy yuborish bo'lmadi (dublikatsiz)", len(channel_calls_repeat), 0)

    print("\n" + "=" * 50)
    if _failures:
        print(f"XATOLAR: {len(_failures)} ta: {_failures}")
        sys.exit(1)
    else:
        print("BARCHA KANALGA ULASHISH VA NATIJALAR SINOVLARI MUVAFFAQQIYATLI O'TDI!")


if __name__ == "__main__":
    asyncio.run(main())
