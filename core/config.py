"""
Konfiguratsiya — `.env` dan o'qiladi, tekshiriladi, tipizatsiya qilinadi.

Tamoyil: **fail-fast**. Noto'g'ri sozlama bo'lsa bot umuman ishga tushmaydi
va aniq xato matnini ko'rsatadi. "Ishladi, lekin nimadir noto'g'ri" holati
bo'lmasligi kerak.

Foydalanish:
    from core.config import settings
    print(settings.bot.token)
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ----------------------------------------------------------------------
#  Kataloglar
# ----------------------------------------------------------------------

#  .../testlab/core/config.py  ->  .../testlab
BASE_DIR: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = BASE_DIR / "data"
LOGS_DIR: Path = BASE_DIR / "logs"
ASSETS_DIR: Path = BASE_DIR / "assets"
FONTS_DIR: Path = ASSETS_DIR / "fonts"
GENERATED_DIR: Path = ASSETS_DIR / "generated"
EXPORTS_DIR: Path = BASE_DIR / "exports"

for _directory in (DATA_DIR, LOGS_DIR, ASSETS_DIR, FONTS_DIR, GENERATED_DIR, EXPORTS_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

ENV_FILE: Path = BASE_DIR / ".env"
DYNAMIC_SETTINGS_FILE: Path = DATA_DIR / "system_settings.json"


def load_dynamic_settings() -> dict[str, Any]:
    """Admin panel orqali o'zgartirilgan dinamik sozlamalarni yuklaydi."""
    if DYNAMIC_SETTINGS_FILE.exists():
        try:
            import json
            return json.loads(DYNAMIC_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_dynamic_setting(key: str, value: Any) -> None:
    """Dinamik sozlamani saqlaydi."""
    import json
    settings_dict = load_dynamic_settings()
    settings_dict[key] = value
    DYNAMIC_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DYNAMIC_SETTINGS_FILE.write_text(json.dumps(settings_dict, indent=2), encoding="utf-8")


# ======================================================================
#  SOZLAMA GURUHLARI
# ======================================================================

class BotSettings(BaseSettings):
    """Telegram bot sozlamalari."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    token: str = Field(alias="BOT_TOKEN")
    username: str = Field(default="TestLabBot", alias="BOT_USERNAME")
    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    super_admin_ids: str = Field(default="", alias="SUPER_ADMIN_IDS")
    required_channels: str = Field(default="", alias="REQUIRED_CHANNELS")

    @field_validator("token")
    @classmethod
    def _check_token(cls, value: str) -> str:
        """Token formatini tekshiradi: '<raqam>:<sir>'."""
        value = value.strip()

        if value.count(":") != 1:
            raise ValueError(
                "BOT_TOKEN formati noto'g'ri.\n"
                "   To'g'ri ko'rinish: 123456789:AAEhBOweik6ad9r_QwErTy...\n"
                "   Tokenni @BotFather dan oling."
            )

        bot_id, secret = value.split(":", 1)
        if not bot_id.isdigit() or len(secret) < 20:
            raise ValueError(
                "BOT_TOKEN yaroqsiz ko'rinadi.\n"
                "   @BotFather bergan tokenni TO'LIQ nusxalang (bo'sh joysiz)."
            )
        return value

    @field_validator("username")
    @classmethod
    def _clean_username(cls, value: str) -> str:
        return value.strip().lstrip("@")

    @property
    def admins(self) -> frozenset[int]:
        """
        `.env` dagi asosiy adminlar ro'yxati.

        Bu "tug'ma" adminlar — ular bazadagi roldan qat'i nazar admin
        bo'lib qoladi. Bazadan admin rolini tasodifan olib tashlash
        botni boshqarib bo'lmaydigan holatga tushirmasligi uchun.
        """
        result: set[int] = set()

        for chunk in self.admin_ids.replace(";", ",").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if not chunk.lstrip("-").isdigit():
                raise ValueError(
                    f"ADMIN_IDS ichidagi '{chunk}' raqam emas.\n"
                    f"   Format: ADMIN_IDS=123456789,987654321\n"
                    f"   ID'ni @userinfobot dan oling."
                )
            result.add(int(chunk))

        return frozenset(result)

    @property
    def super_admins(self) -> frozenset[int]:
        """
        `.env` dagi Bosh Administratorlar (Super Adminlar) ro'yxati.

        Agar SUPER_ADMIN_IDS ko'rsatilmagan bo'lsa, ADMIN_IDS dagi
        birinchi administrator avtomatik ravishda Super Admin hisoblanadi.
        """
        result: set[int] = set()
        raw = self.super_admin_ids.strip()
        if not raw and self.admins:
            return frozenset([next(iter(self.admins))])

        for chunk in raw.replace(";", ",").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if not chunk.lstrip("-").isdigit():
                raise ValueError(
                    f"SUPER_ADMIN_IDS ichidagi '{chunk}' raqam emas.\n"
                    f"   Format: SUPER_ADMIN_IDS=123456789\n"
                    f"   ID'ni @userinfobot dan oling."
                )
            result.add(int(chunk))

        return frozenset(result)

    @property
    def channels(self) -> tuple[str, ...]:
        """
        Majburiy obuna kanallari.

        Bo'sh bo'lsa — tekshiruv umuman ishlamaydi. Kanal qo'shish uchun
        faqat `.env` o'zgaradi, kodga tegilmaydi.
        """
        return tuple(
            chunk.strip()
            for chunk in self.required_channels.replace(";", ",").split(",")
            if chunk.strip()
        )

    @property
    def subscription_required(self) -> bool:
        """Majburiy obuna yoqilganmi?"""
        return bool(self.channels)

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admins or telegram_id in self.super_admins

    def is_super_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.super_admins

    def deep_link(self, payload: str) -> str:
        """Botga havola yasaydi: t.me/bot?start=<payload>"""
        return f"https://t.me/{self.username}?start={payload}"


class DatabaseSettings(BaseSettings):
    """Ma'lumotlar bazasi sozlamalari."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(
        default="sqlite+aiosqlite:///data/testlab.db",
        alias="DATABASE_URL",
    )
    echo: bool = Field(default=False, alias="DATABASE_ECHO")

    @field_validator("url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """
        1. SQLite uchun nisbiy yo'lni absolyutga aylantiradi.
        2. Render / Neon / Supabase bergan postgres:// yoki postgresql://
           ni asyncpg drayveriga (postgresql+asyncpg://) avtomatik moslaydi.
        """
        prefix = "sqlite+aiosqlite:///"

        #  To'rt slash = allaqachon absolyut yo'l
        if value.startswith(prefix) and not value.startswith(prefix + "/"):
            relative = value[len(prefix):]
            absolute = (BASE_DIR / relative).resolve()
            absolute.parent.mkdir(parents=True, exist_ok=True)
            return f"{prefix}{absolute.as_posix()}"

        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+asyncpg://", 1)
        elif value.startswith("postgresql://") and "+asyncpg" not in value:
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Neon / Supabase query parametrlarini asyncpg uchun tozalash
        if "postgresql+asyncpg://" in value:
            import re
            value = re.sub(r"[&?]channel_binding=[^&]*", "", value)
            value = value.replace("sslmode=", "ssl=")
            if "?" not in value and "&" in value:
                value = value.replace("&", "?", 1)

        return value

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.url

    @property
    def sync_url(self) -> str:
        """Alembic uchun sinxron URL (async drayversiz)."""
        return (
            self.url
            .replace("+aiosqlite", "")
            .replace("+asyncpg", "+psycopg2")
            .replace("?ssl=", "?sslmode=")
            .replace("&ssl=", "&sslmode=")
        )


class RedisSettings(BaseSettings):
    """Redis — ixtiyoriy."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(default="", alias="REDIS_URL")

    @property
    def enabled(self) -> bool:
        return bool(self.url.strip())


class TestSettings(BaseSettings):
    """Test tizimi qoidalari."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_questions: int = Field(default=200, ge=1, le=1000, alias="MAX_QUESTIONS")
    pass_score: int = Field(default=60, ge=0, le=100, alias="DEFAULT_PASS_SCORE")
    max_attempts: int = Field(default=1, ge=0, le=100, alias="DEFAULT_MAX_ATTEMPTS")


class SecuritySettings(BaseSettings):
    """Rate limiting va himoya."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    throttle_rate: int = Field(default=20, ge=1, le=1000, alias="THROTTLE_RATE")
    throttle_period: int = Field(default=10, ge=1, le=3600, alias="THROTTLE_PERIOD")


class AppSettings(BaseSettings):
    """Umumiy sozlamalar."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = Field(default="TestLab", alias="PROJECT_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    timezone_offset: int = Field(default=5, ge=-12, le=14, alias="TIMEZONE_OFFSET")

    @field_validator("log_level")
    @classmethod
    def _check_level(cls, value: str) -> str:
        value = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if value not in allowed:
            raise ValueError(
                f"LOG_LEVEL noto'g'ri: '{value}'.\n"
                f"   Ruxsat etilgan: {', '.join(sorted(allowed))}"
            )
        return value


class WebAppSettings(BaseSettings):
    """Telegram Mini App (Web App) sozlamalari."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=True, alias="WEBAPP_ENABLED")
    host: str = Field(default="0.0.0.0", alias="WEBAPP_HOST")
    port: int = Field(default=8088, alias="WEBAPP_PORT")
    url: str = Field(default="http://localhost:8088", alias="WEBAPP_URL")
    auto_tunnel: bool = Field(default=True, alias="WEBAPP_AUTO_TUNNEL")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        import os
        if "WEBAPP_PORT" not in os.environ and "PORT" in os.environ:
            try:
                self.port = int(os.environ["PORT"])
            except ValueError:
                pass
        dyn = load_dynamic_settings()
        if "WEBAPP_ENABLED" in dyn:
            self.enabled = bool(dyn["WEBAPP_ENABLED"])

    @property
    def base_url(self) -> str:
        return self.url.rstrip("/")



class GeminiSettings(BaseSettings):
    """Google Gemini AI sozlamalari."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(default="", alias="GEMINI_API_KEY")
    model: str = Field(default="gemini-flash-lite-latest", alias="GEMINI_MODEL")


# ======================================================================
#  YIG'MA SOZLAMALAR
# ======================================================================

class Settings:
    """
    Barcha sozlamalar bitta joyda.

    Guruhlarga bo'lingan — `settings.bot.token`, `settings.db.url`.
    Bu tekis ro'yxatdan afzal: qaysi sozlama nimaga tegishli ekani
    nomining o'zidan ko'rinadi.
    """

    __slots__ = ("bot", "db", "redis", "test", "security", "app", "webapp", "gemini")

    def __init__(self) -> None:
        self.bot = BotSettings()
        self.db = DatabaseSettings()
        self.redis = RedisSettings()
        self.test = TestSettings()
        self.security = SecuritySettings()
        self.app = AppSettings()
        self.webapp = WebAppSettings()
        self.gemini = GeminiSettings()


        #  Xossalar ichida ValueError chiqishi mumkin — uni HOZIR
        #  chaqirib ko'ramiz, keyinroq kutilmaganda emas.
        _ = self.bot.admins
        _ = self.bot.channels

    # --- Kataloglar (qulaylik uchun) ---
    base_dir = BASE_DIR
    data_dir = DATA_DIR
    logs_dir = LOGS_DIR
    fonts_dir = FONTS_DIR
    generated_dir = GENERATED_DIR
    exports_dir = EXPORTS_DIR


def _print_fatal(title: str, details: str) -> None:
    """Konfiguratsiya xatosini o'qishga qulay ko'rinishda chiqaradi."""
    line = "=" * 62
    print(f"\n{line}", file=sys.stderr)
    print(f"  ❌  {title}", file=sys.stderr)
    print(line, file=sys.stderr)
    print(f"\n{details}\n", file=sys.stderr)

    if not ENV_FILE.exists():
        print(f"  ⚠️  '.env' fayli topilmadi: {ENV_FILE}", file=sys.stderr)
        print("      Windows:  copy .env.example .env", file=sys.stderr)
        print("      Linux:    cp .env.example .env\n", file=sys.stderr)

    print(line + "\n", file=sys.stderr)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Sozlamalarni yuklaydi (bir marta — natija keshlanadi).

    Xato bo'lsa dastur to'xtaydi.
    """
    try:
        return Settings()

    except ValidationError as error:
        problems: list[str] = []
        for item in error.errors():
            field = " → ".join(str(part) for part in item["loc"]) or "?"
            problems.append(f"  • {field}\n    {item['msg']}")
        _print_fatal("KONFIGURATSIYA XATOSI", "\n\n".join(problems))
        raise SystemExit(1) from error

    except ValueError as error:
        _print_fatal("KONFIGURATSIYA XATOSI", f"  {error}")
        raise SystemExit(1) from error


settings: Settings = get_settings()
