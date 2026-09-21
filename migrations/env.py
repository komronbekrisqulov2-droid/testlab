"""
Alembic muhiti.

Muhim jihatlar:

1. Baza manzili `.env` dagi `DATABASE_URL` dan olinadi â€” bot va alembic
   doim bir xil bazaga ishlaydi.

2. Async drayver sinxronga almashtiriladi (`settings.db.sync_url`) â€”
   alembic sinxron ishlaydi.

3. SQLite uchun `render_as_batch=True` MAJBURIY: SQLite `ALTER TABLE`
   ni deyarli qo'llab-quvvatlamaydi, alembic jadvalni qayta yaratib
   ma'lumotni ko'chiradi ("batch" rejimi).

4. `target_metadata` â€” `modules.registry` orqali yig'iladi. Yangi model
   qo'shsangiz reyestrga qo'shishni unutmang, aks holda autogenerate
   uni ko'rmaydi.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

#  Loyiha ildizini import yo'liga qo'shamiz
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#  DIQQAT: `core.config` `.env` ni tekshiradi. To'ldirilmagan bo'lsa
#  aniq xato matni chiqadi va jarayon to'xtaydi.
#  Yechim:  copy .env.example .env
try:
    from core.config import settings
    from modules.registry import Base
except SystemExit:
    print(
        "\n  Alembic ishga tushmadi: '.env' to'ldirilmagan.\n"
        "     Windows:  copy .env.example .env\n"
        "     Linux:    cp .env.example .env\n",
        file=sys.stderr,
    )
    raise

config = context.config
config.set_main_option("sqlalchemy.url", settings.db.sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context) -> str | bool:
    """
    Ba'zi tiplarni migratsiya fayliga qanday yozishni belgilaydi.

    NIMA UCHUN KERAK
    ----------------
    `JSON().with_variant(JSONB(), "postgresql")` ni alembic shunday
    chiqaradi:

        postgresql.JSONB(astext_type=Text())
                                     ^^^^^^ `sa.` prefiksisiz!

    Natijada migratsiya `NameError: name 'Text' is not defined` bilan
    to'xtaydi. `astext_type` baribir standart qiymat, shuning uchun uni
    umuman yozmaymiz.
    """
    import sqlalchemy as sa

    if type_ == "type" and isinstance(obj, sa.JSON):
        autogen_context.imports.add("import sqlalchemy as sa")
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')"

    #  False = alembic o'zi hal qilsin
    return False


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """
    Autogenerate qaysi obyektlarni hisobga olishini hal qiladi.

    Alembic'ning o'z xizmatchi jadvali va SQLite ichki jadvallari
    chetlab o'tiladi â€” aks holda har autogenerate ularni o'chirishga
    urinadi.
    """
    if type_ == "table" and name in {"alembic_version", "sqlite_sequence"}:
        return False
    return True


def run_migrations_offline() -> None:
    """
    Bazaga ulanmasdan SQL matnini chiqaradi.

    Foydali holat: production bazasini DBA qo'lida yangilash.
        alembic upgrade head --sql > migration.sql
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
        render_item=render_item,
        render_as_batch=settings.db.is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Bazaga ulanib migratsiyalarni bajaradi."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
            render_item=render_item,
            render_as_batch=settings.db.is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
