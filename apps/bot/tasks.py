"""
Fon vazifalari — hech kim tugma bosmasa ham bajarilishi kerak bo'lgan ishlar.

NEGA KERAK
----------
Ikki narsa foydalanuvchining harakatini kutib turolmaydi:

  * **Vaqt chegarasi.** O'quvchi testni ochib, javob yubormasdan
    chiqib ketsa, urinish `IN_PROGRESS` holatida abadiy osilib
    qolardi: na natija, na yangi urinish. `deadline` maydoni bor edi,
    lekin uni tekshiradigan hech kim yo'q edi.

  * **Test jadvali.** O'qituvchi `starts_at` / `ends_at` qo'yadi va
    yarim tunda tugma bosib o'tirishi kerak emas.

QOIDALAR
--------
1. Har bir vazifa O'Z sessiyasida ishlaydi (`get_session`) — handler
   sessiyasidan mustaqil.
2. Xato ichkarida ushlanadi: bitta vazifa yiqilsa rejalashtiruvchi
   to'xtamasligi va qolgan vazifalar ishlashda davom etishi kerak.
3. Xabar yuborish bazadan TASHQARIDA, sessiya yopilgach bajariladi —
   Telegram sekin javob bersa, baza tranzaksiyasi ochiq turmasin.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from apps.bot.texts import uz
from core.datetime_utils import LOCAL_TZ, utcnow
from core.logging import get_logger
from infrastructure.database.engine import get_session
from modules.assessment.repository import AttemptRepository
from modules.assessment.service import AssessmentService
from modules.catalog.service import CatalogService
from modules.identity.repository import UserRepository

log = get_logger(__name__)

#  Har daqiqada tekshirish yetarli: vaqt chegarasi daqiqalarda
#  o'lchanadi va bir daqiqalik kechikish sezilmaydi. Tez-tez
#  so'ramaslik SQLite'ni ham keraksiz qulflardan saqlaydi.
CHECK_INTERVAL_SEC = 60

#  Telegram sekundiga ~30 xabarga ruxsat beradi. Fon vazifasi
#  o'quvchilar bilan jonli suhbatni bo'g'ib qo'ymasligi kerak.
NOTIFY_DELAY_SEC = 0.05


# ======================================================================
#  XABAR YUBORISH
# ======================================================================

async def _notify_all(bot: Bot, targets: list[tuple[int, str]]) -> int:
    """
    Bildirishnomalarni yuboradi.

    Xato jimgina o'tkazib yuboriladi: foydalanuvchi botni bloklagan
    bo'lishi mumkin — bu normal holat va fon vazifasini to'xtatmasligi
    kerak.

    Returns:
        Muvaffaqiyatli yuborilganlar soni.
    """
    sent = 0

    for telegram_id, text in targets:
        try:
            await bot.send_message(telegram_id, text)
            sent += 1
        except Exception as error:
            log.debug("Bildirishnoma yetkazilmadi (%s): %s", telegram_id, error)

        await asyncio.sleep(NOTIFY_DELAY_SEC)

    return sent


# ======================================================================
#  VAZIFA 1 — MUDDATI O'TGAN URINISHLAR
# ======================================================================

async def expire_overdue_attempts(bot: Bot) -> None:
    """Vaqti tugagan urinishlarni yopadi va o'quvchilarga xabar beradi."""
    try:
        async with get_session() as session:
            expired = await AssessmentService(session).expire_overdue()

            #  Xabar matnini sessiya ICHIDA tayyorlaymiz — bog'lanishlar
            #  shu yerda yuklangan, tashqarida ularga murojaat qilish
            #  qo'shimcha so'rov talab qilardi.
            targets = [
                (attempt.user.telegram_id, uz.attempt_expired(attempt.test))
                for attempt in expired
                if attempt.user is not None
                and attempt.test is not None
                and attempt.user.notifications_enabled
                and not attempt.user.is_banned
            ]

    except Exception as error:
        log.exception("Urinishlarni yopishda xato: %s", error)
        return

    if targets:
        await _notify_all(bot, targets)


# ======================================================================
#  VAZIFA 2 — TEST JADVALI
# ======================================================================

async def apply_test_schedule(bot: Bot) -> None:
    """Vaqti kelgan testlarni ochadi, muddati tugaganini arxivlaydi va kanalga natijalarni e'lon qiladi."""
    targets: list[tuple[int, str]] = []
    channel_posts: list[tuple[int, int, int, int | None, str]] = []

    try:
        async with get_session() as session:
            catalog = CatalogService(session)

            opened = await catalog.open_scheduled()
            closed = await catalog.close_expired()

            if not opened and not closed:
                return

            users = UserRepository(session)
            attempt_repo = AttemptRepository(session)

            announcements = [(test, uz.test_auto_opened(test)) for test in opened]
            announcements += [(test, uz.test_auto_closed(test)) for test in closed]

            for test, text in announcements:
                if test.author_id is None:
                    continue

                author = await users.get(test.author_id)
                if author is None or author.is_banned:
                    continue
                if not author.notifications_enabled:
                    continue

                targets.append((author.telegram_id, text))

            # Kanal/Guruhga avtomatik yakuniy natijalarni (Top-10) chiqarish
            for test in closed:
                if test.channel_id and not test.results_posted_at:
                    page = await attempt_repo.list_by_test(test.id, page=1, per_page=10, by_rank=True)
                    total = await attempt_repo.count_finished_by_test(test.id)
                    leaderboard_text = uz.channel_leaderboard(test, page.items, total)
                    channel_posts.append((test.id, test.number, test.channel_id, test.channel_message_id, leaderboard_text))
                    test.results_posted_at = utcnow()

            if channel_posts:
                await session.commit()

    except Exception as error:
        log.exception("Test jadvalini qo'llashda xato: %s", error)
        return

    if targets:
        await _notify_all(bot, targets)

    for _tid, test_number, channel_id, channel_msg_id, text in channel_posts:
        try:
            try:
                await bot.send_message(
                    chat_id=channel_id,
                    text=text,
                    reply_to_message_id=channel_msg_id if channel_msg_id else None,
                )
            except Exception:
                await bot.send_message(chat_id=channel_id, text=text)
            log.info(
                "№%s test natijalari kanalga avtomatik e'lon qilindi (channel_id=%s)",
                test_number,
                channel_id,
            )
        except Exception as err:
            log.warning("Kanalga avtomatik natija e'lon qilishda xatolik (%s): %s", channel_id, err)
        await asyncio.sleep(NOTIFY_DELAY_SEC)



# ======================================================================
#  ROSTLASH
# ======================================================================

def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Rejalashtiruvchini yig'adi (hali ishga tushirmaydi).

    `coalesce=True` + `misfire_grace_time` — bot uzoq o'chib turgandan
    keyin o'tkazib yuborilgan yuzlab yurishni birdaniga bajarmaydi,
    faqat bittasini ishlatadi. Aks holda qayta ishga tushish paytida
    bot o'zini o'zi DDoS qilardi.

    `max_instances=1` — oldingi yurish tugamagan bo'lsa yangisi
    boshlanmaydi: ikkita vazifa bir xil urinishni yopishga urinmasin.
    """
    scheduler = AsyncIOScheduler(timezone=LOCAL_TZ)

    common = dict(
        trigger="interval",
        seconds=CHECK_INTERVAL_SEC,
        args=[bot],
        max_instances=1,
        coalesce=True,
        misfire_grace_time=CHECK_INTERVAL_SEC,
        replace_existing=True,
    )

    scheduler.add_job(expire_overdue_attempts, id="expire_attempts", **common)
    scheduler.add_job(apply_test_schedule, id="test_schedule", **common)

    return scheduler
