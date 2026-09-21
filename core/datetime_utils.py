"""
Vaqt bilan ishlash.

QOIDA: bazada **hamma vaqt UTC**da va **naive** (mintaqasiz) saqlanadi.
Foydalanuvchiga ko'rsatishdan oldingina mahalliy vaqtga o'giriladi.

Nega shunday? Mintaqali (aware) vaqtni SQLite va PostgreSQL turlicha
saqlaydi — aralashtirilsa taqqoslash jimgina noto'g'ri natija beradi.
Bitta qoida — bitta xatti-harakat.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from core.config import settings

#  Mahalliy mintaqa — `.env` dagi TIMEZONE_OFFSET dan
LOCAL_TZ = timezone(timedelta(hours=settings.app.timezone_offset))

#  O'zbekcha oy nomlari (sertifikat va hisobotlar uchun)
MONTHS_UZ: tuple[str, ...] = (
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
)

WEEKDAYS_UZ: tuple[str, ...] = (
    "dushanba", "seshanba", "chorshanba", "payshanba",
    "juma", "shanba", "yakshanba",
)


# ----------------------------------------------------------------------
#  Olish va o'girish
# ----------------------------------------------------------------------

def utcnow() -> datetime:
    """Hozirgi UTC vaqt, naive ko'rinishda. Bazaga shu yoziladi."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(value: datetime | None) -> datetime | None:
    """Bazadagi naive-UTC vaqtni mahalliy vaqtga o'giradi."""
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(LOCAL_TZ)


def local_date(value: datetime | None = None) -> date:
    """
    Mahalliy kalendar sanasi.

    Seriya (streak) hisobi uchun kerak: «ketma-ket kunlar» — bu
    foydalanuvchining kunlari, UTC kunlari emas. UTC bo'yicha
    hisoblansa, kechqurun 05:30 dan keyin yechilgan test ertangi kunga
    o'tib ketardi va seriya haqsiz uzilardi.
    """
    local = to_local(value if value is not None else utcnow())
    assert local is not None
    return local.date()


def to_utc_naive(value: datetime | None) -> datetime | None:
    """Istalgan vaqtni bazaga yoziladigan ko'rinishga keltiradi."""
    if value is None:
        return None
    if value.tzinfo is None:
        #  Mintaqasiz kelgan vaqt mahalliy deb qabul qilinadi
        value = value.replace(tzinfo=LOCAL_TZ)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def parse_datetime_input(text: str) -> datetime | None:
    """
    Foydalanuvchi kiritgan vaqt matnini (masalan '14:30', '22.09 18:00', '22.09.2026 18:00')
    tahlil qilib, bazaga yoziladigan UTC naive datetime qaytaradi.
    """
    text = text.strip()
    now_local = to_local(utcnow())
    if not now_local:
        return None

    # Format 1: HH:MM (masalan '14:30')
    if ":" in text and len(text.split()) == 1:
        try:
            parts = text.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                dt_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return to_utc_naive(dt_local)
        except Exception:
            pass

    # Format 2: DD.MM.YYYY HH:MM
    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            dt_local = dt.replace(tzinfo=LOCAL_TZ)
            return to_utc_naive(dt_local)
        except ValueError:
            pass

    # Format 3: DD.MM HH:MM (joriy yil olinadi)
    for fmt in ("%d.%m %H:%M", "%d/%m %H:%M"):
        try:
            dt = datetime.strptime(f"{text} {now_local.year}", f"{fmt} %Y")
            dt_local = dt.replace(tzinfo=LOCAL_TZ)
            return to_utc_naive(dt_local)
        except ValueError:
            pass

    return None


# ----------------------------------------------------------------------
#  Formatlash
# ----------------------------------------------------------------------

def fmt_date(value: datetime | None) -> str:
    """'01.08.2026'"""
    local = to_local(value)
    return local.strftime("%d.%m.%Y") if local else "—"


def fmt_datetime(value: datetime | None, *, seconds: bool = False) -> str:
    """'01.08.2026 14:30'"""
    local = to_local(value)
    if local is None:
        return "—"
    return local.strftime("%d.%m.%Y %H:%M:%S" if seconds else "%d.%m.%Y %H:%M")


def fmt_date_uz(value: datetime | None) -> str:
    """'1-avgust, 2026-yil' — sertifikat uchun."""
    local = to_local(value)
    if local is None:
        return "—"
    return f"{local.day}-{MONTHS_UZ[local.month - 1]}, {local.year}-yil"


def fmt_duration(seconds: int | float | None) -> str:
    """
    Davomiylikni o'zbekcha yozadi.

        45      -> '45 soniya'
        330     -> '5 daqiqa 30 soniya'
        3900    -> '1 soat 5 daqiqa'
    """
    if seconds is None:
        return "—"

    total = int(max(0, seconds))

    if total < 60:
        return f"{total} soniya"

    minutes, secs = divmod(total, 60)

    if minutes < 60:
        return f"{minutes} daqiqa" + (f" {secs} soniya" if secs else "")

    hours, minutes = divmod(minutes, 60)
    return f"{hours} soat" + (f" {minutes} daqiqa" if minutes else "")


def fmt_timer(seconds: int | float | None) -> str:
    """Taymer ko'rinishi: '05:30' yoki '1:05:30'."""
    if seconds is None:
        return "--:--"

    total = int(max(0, seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def fmt_relative(value: datetime | None) -> str:
    """
    Nisbiy vaqt: 'hozirgina', '5 daqiqa oldin', 'kecha', '3 kun oldin'.
    """
    if value is None:
        return "—"

    delta = utcnow() - value
    total = int(delta.total_seconds())

    if total < 0:
        return fmt_datetime(value)
    if total < 60:
        return "hozirgina"
    if total < 3600:
        return f"{total // 60} daqiqa oldin"
    if total < 86_400:
        return f"{total // 3600} soat oldin"
    if total < 172_800:
        return "kecha"
    if total < 604_800:
        return f"{total // 86_400} kun oldin"
    if total < 2_592_000:
        return f"{total // 604_800} hafta oldin"

    return fmt_date(value)


# ----------------------------------------------------------------------
#  Davrlar (hisobotlar uchun)
# ----------------------------------------------------------------------

def start_of_day(value: datetime | None = None) -> datetime:
    """Kun boshi (mahalliy), UTC-naive ko'rinishda qaytadi."""
    local = to_local(value or utcnow())
    assert local is not None
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return to_utc_naive(midnight)  # type: ignore[return-value]


def days_ago(days: int) -> datetime:
    """N kun oldingi vaqt."""
    return utcnow() - timedelta(days=days)


def start_of_week() -> datetime:
    """Joriy haftaning dushanbasi."""
    local = to_local(utcnow())
    assert local is not None
    monday = local - timedelta(days=local.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return to_utc_naive(monday)  # type: ignore[return-value]


def start_of_month() -> datetime:
    """Joriy oyning birinchi kuni."""
    local = to_local(utcnow())
    assert local is not None
    first = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return to_utc_naive(first)  # type: ignore[return-value]
