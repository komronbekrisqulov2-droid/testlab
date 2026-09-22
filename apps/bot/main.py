"""
Bot — kirish nuqtasi.

Ishga tushirish:
    python run.py

To'xtatish: Ctrl + C (barcha ulanishlar toza yopiladi)
"""

from __future__ import annotations

import asyncio
import platform
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

from apps.bot.handlers import setup_routers
from apps.bot.middlewares import setup_middlewares
from apps.bot.tasks import setup_scheduler
from core.config import settings
from core.logging import get_logger, log_banner, setup_logging
from infrastructure.database.engine import close_database, init_database

log = get_logger(__name__)

#  Fon vazifalari rejalashtiruvchisi. Modul darajasida saqlanadi:
#  `on_startup` uni yaratadi, `on_shutdown` to'xtatadi — aiogram
#  hayotiy sikl handlerlari orasida obyekt uzatish yo'li yo'q.
_scheduler = None
_webapp_runner = None
_tunnel_urls = None



BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="🚀 Botni ishga tushirish"),
    BotCommand(command="menu", description="🏠 Bosh menyu"),
    BotCommand(command="new", description="➕ Test yaratish"),
    BotCommand(command="profile", description="👤 Profilim"),
    BotCommand(command="help", description="❓ Yordam"),
    BotCommand(command="cancel", description="✖️ Amalni bekor qilish"),
]


def create_bot() -> Bot:
    """Bot obyektini yaratadi."""
    return Bot(
        token=settings.bot.token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            #  Havola ko'rinishi o'chirilgan: test matnida havola bo'lsa
            #  ekranni egallab, xabarni chalkashtirib yuborardi
            link_preview_is_disabled=True,
        ),
    )


def create_storage():
    """
    FSM saqlash joyi.

    Redis bo'lsa — holatlar bot qayta ishga tushgach ham saqlanadi.
    Bo'lmasa xotira: sodda, lekin restartda holat yo'qoladi.
    """
    if not settings.redis.enabled:
        log.info("💾 FSM: xotira rejimi (Redis o'chirilgan)")
        return MemoryStorage()

    try:
        from aiogram.fsm.storage.redis import RedisStorage

        storage = RedisStorage.from_url(settings.redis.url)
        log.info("💾 FSM: Redis")
        return storage

    except Exception as error:
        #  Redis ishlamasa bot to'xtamasligi kerak — xotiraga tushamiz
        log.warning("Redis ulanmadi (%s) — xotira rejimiga o'tildi", error)
        return MemoryStorage()


async def set_commands(bot: Bot) -> None:
    """Telegram menyusidagi buyruqlar ro'yxati."""
    try:
        await bot.set_my_commands(
            BOT_COMMANDS, scope=BotCommandScopeAllPrivateChats()
        )
        log.info("⌨️  Buyruqlar o'rnatildi (%d ta)", len(BOT_COMMANDS))
    except Exception as error:
        log.warning("Buyruqlarni o'rnatib bo'lmadi: %s", error)


# ======================================================================
#  HAYOTIY SIKL
# ======================================================================

async def on_startup(bot: Bot) -> None:
    """
    Bot ishga tushganda.

    DIQQAT: parametr nomi ATAYLAB `bot` — aiogram hayotiy sikl
    handlerlariga argumentlarni NOM BO'YICHA uzatadi. Nomni
    o'zgartirsangiz `TypeError: missing 1 required positional argument`
    chiqadi.
    """
    log.info("🚀 Ishga tushmoqda...")

    await init_database()
    await _seed_defaults()
    await set_commands(bot)
    _start_scheduler(bot)
    await _start_webapp(bot)

    me = await bot.get_me()
    log_banner(log, username=me.username or "?", bot_id=me.id)


    await _notify_admins(bot, me.username or "?")


def _start_scheduler(bot: Bot) -> None:
    """
    Fon vazifalarini ishga tushiradi.

    Xato bo'lsa bot TO'XTAMAYDI: rejalashtiruvchisiz ham botning
    asosiy ishi — javob qabul qilish — buzilmaydi. Vaqt chegarasi va
    jadval ishlamay qoladi, xolos, va bu haqda log'da ogohlantirish
    turadi.
    """
    global _scheduler

    try:
        _scheduler = setup_scheduler(bot)
        _scheduler.start()
        log.info("⏱  Fon vazifalari ishga tushdi (%d ta)", len(_scheduler.get_jobs()))
    except Exception as error:
        _scheduler = None
        log.warning("Fon vazifalari ishga tushmadi: %s", error)


async def _start_webapp(bot: Bot) -> None:
    """Telegram Mini App serverini ishga tushiradi."""
    global _webapp_runner, _tunnel_urls
    if not settings.webapp.enabled:
        return
    try:
        from apps.webapp.server import start_webapp_server

        _webapp_runner = await start_webapp_server(
            bot=bot,
            host=settings.webapp.host,
            port=settings.webapp.port,
        )

        if settings.webapp.auto_tunnel and not settings.webapp.url.startswith("https://"):
            try:
                import asyncio
                from core.tunnel import start_cloudflare_tunnel

                loop = asyncio.get_running_loop()
                tunnel_url = await loop.run_in_executor(
                    None,
                    lambda: start_cloudflare_tunnel(port=settings.webapp.port),
                )
                if tunnel_url:
                    settings.webapp.url = tunnel_url
                    log.info("🌐 Web App HTTPS Tunnel tayyor: %s", tunnel_url)
            except Exception as tunnel_err:
                log.warning("Web App HTTPS tunnel ulanmadi (lokal rejimda davom etiladi): %s", tunnel_err)

    except Exception as error:
        log.warning("Web App server ishga tushmadi: %s", error)



async def _seed_defaults() -> None:
    """Boshlang'ich kategoriyalarni qo'shadi (bo'sh bazada)."""
    from infrastructure.database.engine import get_session
    from modules.catalog.repository import CategoryRepository

    async with get_session() as session:
        added = await CategoryRepository(session).seed_defaults()
        if added:
            log.info("🌱 %d ta kategoriya qo'shildi", added)


async def _notify_admins(bot: Bot, username: str) -> None:
    """Adminlarga bot ishga tushgani haqida xabar."""
    if not settings.bot.admins:
        return

    text = (
        f"🟢 <b>Bot ishga tushdi</b>\n\n"
        f"@{username}\n"
        f"Baza: {'PostgreSQL' if settings.db.is_postgres else 'SQLite'}\n"
        f"Redis: {'yoqilgan' if settings.redis.enabled else 'o‘chirilgan'}\n"
        f"Obuna: {'yoqilgan' if settings.bot.subscription_required else 'o‘chirilgan'}\n\n"
        f"<i>Admin panel: /admin</i>"
    )

    for admin_id in settings.bot.admins:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            #  Admin hali botga /start bosmagan bo'lishi mumkin — normal
            continue


async def on_shutdown(bot: Bot) -> None:
    """Bot to'xtaganda — hamma narsa toza yopiladi."""
    log.info("🛑 To'xtatilmoqda...")

    #  Rejalashtiruvchi bazadan OLDIN to'xtatiladi: ishlab turgan
    #  vazifa yopilgan ulanishga murojaat qilmasin.
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("⏱  Fon vazifalari to'xtatildi")

    global _webapp_runner
    try:
        from core.tunnel import stop_cloudflare_tunnel
        stop_cloudflare_tunnel()
        log.info("🌐 Web App tunnel to'xtatildi")
    except Exception:
        pass

    if _webapp_runner is not None:
        await _webapp_runner.cleanup()
        log.info("🌐 Web App server to'xtatildi")

    await close_database()
    log.info("👋 Xayr!")



# ======================================================================
#  ISHGA TUSHIRISH
# ======================================================================

async def run() -> None:
    """Botni polling rejimida ishga tushiradi."""
    bot = create_bot()
    dispatcher = Dispatcher(storage=create_storage())

    setup_middlewares(dispatcher)
    setup_routers(dispatcher)

    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)

    try:
        #  Bot to'xtagan vaqtda kelgan eski xabarlarni tashlab yuboramiz.
        #  DIQQAT: bu Telegram'ga birinchi murojaat — token noto'g'ri
        #  bo'lsa aynan shu yerda xato chiqadi.
        await bot.delete_webhook(drop_pending_updates=True)

        await dispatcher.start_polling(
            bot, allowed_updates=dispatcher.resolve_used_update_types()
        )
    finally:
        #  Polling boshlanmasa `on_shutdown` chaqirilmaydi va aiohttp
        #  sessiyasi ochiq qoladi ("Unclosed client session").
        #  `close()` takroriy chaqirilishga chidamli.
        try:
            await bot.session.close()
        except Exception:
            pass


def _fatal(title: str, lines: list[str]) -> None:
    """Halokatli xatoni traceback'siz, o'qishga qulay ko'rinishda chiqaradi."""
    border = "=" * 62
    print(f"\n{border}", file=sys.stderr)
    print(f"  ❌  {title}", file=sys.stderr)
    print(border, file=sys.stderr)
    print("", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    print(f"\n{border}\n", file=sys.stderr)


def main() -> None:
    """Sinxron kirish nuqtasi."""
    setup_logging()

    #  Windows'da asyncio uchun mos siklni tanlaymiz
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(run())

    except (KeyboardInterrupt, SystemExit):
        log.info("⌨️  Ctrl+C — to'xtatildi")

    except TelegramUnauthorizedError:
        _fatal(
            "TELEGRAM TOKENNI QABUL QILMADI",
            [
                "'.env' faylidagi BOT_TOKEN noto'g'ri, eskirgan yoki hali",
                "namunaviy qiymatda qolgan.",
                "",
                "YECHIM:",
                "  1) Telegram'da @BotFather ni oching",
                "  2) /mybots -> botingizni tanlang -> API Token",
                "  3) Tokenni TO'LIQ nusxalang (bo'sh joysiz)",
                "  4) '.env' faylida BOT_TOKEN ni almashtiring",
                "  5) Qayta ishga tushiring:  python run.py",
            ],
        )
        sys.exit(1)

    except TelegramNetworkError as error:
        _fatal(
            "TELEGRAM SERVERIGA ULANIB BO'LMADI",
            [
                f"Sabab: {error}",
                "",
                "Tekshiring:",
                "  • Internet aloqasi bormi",
                "  • Telegram bloklangan bo'lsa — VPN kerak",
                "  • Antivirus yoki korporativ tarmoq HTTPS'ni to'smayaptimi",
            ],
        )
        sys.exit(1)

    except Exception as error:
        log.critical("💥 Halokatli xato: %s", error, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
