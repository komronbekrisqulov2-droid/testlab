"""
Loglash sozlamasi.

Ikki chiqish yo'nalishi:
    * konsol — rangli, o'qishga qulay (ishlab chiqish paytida)
    * fayl   — rotatsiyali, batafsil (keyin tahlil qilish uchun)

Windows konsoli standart holda UTF-8 emas, shuning uchun emoji va
o'zbekcha harflar buzilib chiqadi — buni ham hal qilamiz.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from core.config import settings

#  Fayl 5 MB dan oshsa yangisi boshlanadi, 5 tagacha eski nusxa saqlanadi
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

#  Juda "gapiruvchan" kutubxonalarni tinchlantiramiz
NOISY_LOGGERS: tuple[str, ...] = (
    "aiogram.event",
    "aiosqlite",
    "asyncio",
    "apscheduler.executors.default",
)


class ColorFormatter(logging.Formatter):
    """Konsol uchun daraja bo'yicha ranglaydi."""

    COLORS: dict[int, str] = {
        logging.DEBUG:    "\033[36m",  # siyan
        logging.INFO:     "\033[32m",  # yashil
        logging.WARNING:  "\033[33m",  # sariq
        logging.ERROR:    "\033[31m",  # qizil
        logging.CRITICAL: "\033[35m",  # binafsha
    }
    RESET = "\033[0m"

    def __init__(self, *args, use_color: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if not self.use_color:
            return super().format(record)

        color = self.COLORS.get(record.levelno, "")
        original = record.levelname
        record.levelname = f"{color}{original:<8}{self.RESET}"
        try:
            return super().format(record)
        finally:
            #  Yozuvni asl holiga qaytaramiz — fayl handleri ham shu
            #  obyektni ishlatadi va rang kodlari faylga tushmasligi kerak
            record.levelname = original


def _supports_color(stream) -> bool:
    """Terminal rangni qo'llab-quvvatlaydimi?"""
    return hasattr(stream, "isatty") and stream.isatty()


def setup_logging() -> None:
    """Loglashni sozlaydi. Dastur boshida bir marta chaqiriladi."""
    level = getattr(logging, settings.app.log_level, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    #  Qayta chaqirilsa handlerlar ikkilanmasin
    for handler in list(root.handlers):
        root.removeHandler(handler)

    # --- Konsol ---
    #  Windows konsolida emoji buzilmasligi uchun UTF-8 ga o'tkazamiz
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(
        ColorFormatter(
            fmt="%(asctime)s %(levelname)s %(name)-26s %(message)s",
            datefmt="%H:%M:%S",
            use_color=_supports_color(sys.stdout),
        )
    )
    root.addHandler(console)

    # --- Fayl ---
    file_handler = RotatingFileHandler(
        filename=settings.logs_dir / "testlab.log",
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG if level <= logging.DEBUG else logging.INFO)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-28s | %(funcName)-20s:%(lineno)-4d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(file_handler)

    # --- Shovqinni kamaytiramiz ---
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    #  SQL so'rovlari faqat ataylab yoqilganda ko'rinsin
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.db.echo else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """Modul uchun logger qaytaradi."""
    return logging.getLogger(name)


def log_banner(log: logging.Logger, *, username: str, bot_id: int) -> None:
    """Ishga tushganda ko'rinadigan banner."""
    rows = [
        ("Bot", f"@{username}"),
        ("Bot ID", str(bot_id)),
        ("Baza", "PostgreSQL" if settings.db.is_postgres else "SQLite"),
        ("Redis", "yoqilgan" if settings.redis.enabled else "o'chirilgan (xotira)"),
        ("Adminlar", str(len(settings.bot.admins))),
        (
            "Majburiy obuna",
            ", ".join(settings.bot.channels) if settings.bot.subscription_required
            else "o'chirilgan",
        ),
        ("Log darajasi", settings.app.log_level),
    ]

    width = 58
    log.info("")
    log.info("╔" + "═" * width + "╗")
    title = f"🎓  {settings.app.name.upper()}  —  ISHGA TUSHDI"
    log.info("║" + title.center(width - 2) + "  ║")
    log.info("╠" + "═" * width + "╣")
    for label, value in rows:
        log.info("║  %-16s: %-*s║", label, width - 20, value)
    log.info("╚" + "═" * width + "╝")
    log.info("")
