"""
Baza ulanishi: engine, sessiya fabrikasi, ishga tayyorlash.

SQLite va PostgreSQL uchun sozlamalar farq qiladi — ikkalasi ham
shu yerda hisobga olingan.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings
from core.logging import get_logger
from infrastructure.database.base import Base

log = get_logger(__name__)


# ----------------------------------------------------------------------
#  Engine
# ----------------------------------------------------------------------

def _engine_options() -> dict[str, Any]:
    """Baza turiga qarab ulanish sozlamalari."""
    options: dict[str, Any] = {
        "echo": settings.db.echo,
        "future": True,
        #  Ulanish 30 daqiqadan keyin yangilanadi — uzoq turgan ulanishni
        #  server yoki proksi jimgina uzib qo'yishi mumkin
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }

    if settings.db.is_sqlite:
        #  SQLite bitta faylga yozadi. `timeout` — boshqa yozuvchi
        #  qulfni bo'shatguncha kutish vaqti.
        options["connect_args"] = {"timeout": 30, "check_same_thread": False}
    else:
        #  PostgreSQL — ulanishlar hovuzi
        options["pool_size"] = 10
        options["max_overflow"] = 20
        options["pool_timeout"] = 30

    return options


engine: AsyncEngine = create_async_engine(settings.db.url, **_engine_options())

session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ----------------------------------------------------------------------
#  SQLite sozlamalari
# ----------------------------------------------------------------------

if settings.db.is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        """
        Har bir ulanishda SQLite'ni to'g'ri rejimga qo'yadi.

        foreign_keys=ON  — SQLite'da tashqi kalitlar standart holda
                           TEKSHIRILMAYDI. Busiz kaskad o'chirish ishlamaydi
                           va bazada "yetim" yozuvlar qoladi.
        journal_mode=WAL — o'qish va yozish bir-birini bloklamaydi.
        busy_timeout     — qulf bo'shashini kutadi, darhol xato bermaydi.
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA temp_store=MEMORY")
        finally:
            cursor.close()


# ----------------------------------------------------------------------
#  Sessiya
# ----------------------------------------------------------------------

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Sessiya konteksti — bot handlerlaridan TASHQARIDA ishlatiladi
    (fon vazifalari, skriptlar, migratsiya yordamchilari).

    Handler'lar uchun `DatabaseMiddleware` sessiyani o'zi beradi.

        async with get_session() as session:
            ...
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ----------------------------------------------------------------------
#  Ishga tayyorlash
# ----------------------------------------------------------------------

async def check_connection() -> bool:
    """Bazaga ulanib bo'ladimi?"""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception as error:
        log.critical("❌ Bazaga ulanib bo'lmadi: %s", error)
        return False


async def create_tables() -> None:
    """
    Jadvallarni yaratadi (agar yo'q bo'lsa).

    DIQQAT: bu faqat ISHLAB CHIQISH qulayligi. Production'da sxema
    Alembic bilan boshqariladi — `create_all` mavjud jadvalga ustun
    qo'sha olmaydi va sxema o'zgarishini kuzatmaydi.
    """
    #  Modellar import qilinmasa `Base.metadata` bo'sh bo'ladi
    import modules.registry  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    log.info("✅ Jadvallar tayyor (%d ta)", len(Base.metadata.tables))


async def _ensure_columns() -> None:
    """Mavjud jadvallarga yangi ustunlarni zarurat bo'lsa xavfsiz qo'shadi."""
    if not settings.db.is_sqlite:
        return

    async with engine.begin() as connection:
        try:
            res = await connection.execute(text("PRAGMA table_info(tests)"))
            cols = {row[1] for row in res.fetchall()}
            if cols:
                if "channel_id" not in cols:
                    await connection.execute(text("ALTER TABLE tests ADD COLUMN channel_id BIGINT"))
                if "channel_message_id" not in cols:
                    await connection.execute(text("ALTER TABLE tests ADD COLUMN channel_message_id INTEGER"))
                if "results_posted_at" not in cols:
                    await connection.execute(text("ALTER TABLE tests ADD COLUMN results_posted_at DATETIME"))
        except Exception as err:
            log.debug("Ustunlarni tekshirishda xatolik: %s", err)


async def init_database() -> None:
    """Bazani ishga tayyorlaydi. Bot startida chaqiriladi."""
    log.info("🗄  Bazaga ulanmoqda...")

    if not await check_connection():
        raise RuntimeError("Bazaga ulanib bo'lmadi")

    await create_tables()
    await _ensure_columns()


async def close_database() -> None:
    """Ulanishlarni yopadi. Bot to'xtaganda chaqiriladi."""
    await engine.dispose()
    log.info("🗄  Baza ulanishlari yopildi")


async def healthcheck() -> bool:
    """Admin panel va Docker healthcheck uchun."""
    return await check_connection()
