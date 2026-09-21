"""
Shriftlarni yuklash.

Rasm chizishda shrift topilmasligi butun jarayonni to'xtatmasligi kerak,
shuning uchun uch bosqichli zaxira zanjiri ishlatiladi:

    1. Loyihaning `assets/fonts/` katalogi   (loyiha bilan keladi)
    2. Tizim shriftlari (Windows / Linux / macOS)
    3. Pillow'ning ichki shrifti             (har doim mavjud)

Ya'ni sertifikat HAR QANDAY muhitda chiziladi — Docker ichida ham.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)


#  Nisbiy nomlar avval loyiha katalogidan qidiriladi
REGULAR_CANDIDATES: tuple[str, ...] = (
    "DejaVuSans.ttf",
    "Roboto-Regular.ttf",
    "OpenSans-Regular.ttf",
    #  Windows
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    #  Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    #  macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)

BOLD_CANDIDATES: tuple[str, ...] = (
    "DejaVuSans-Bold.ttf",
    "Roboto-Bold.ttf",
    "OpenSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

MONO_CANDIDATES: tuple[str, ...] = (
    "DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)

MONO_BOLD_CANDIDATES: tuple[str, ...] = (
    "DejaVuSansMono-Bold.ttf",
    "C:/Windows/Fonts/consolab.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
)


def _resolve(candidates: tuple[str, ...]) -> str | None:
    """Ro'yxatdagi birinchi mavjud shrift faylini topadi."""
    for candidate in candidates:
        path = Path(candidate)

        #  Nisbiy nom — avval loyiha katalogidan
        if not path.is_absolute():
            local = settings.fonts_dir / candidate
            if local.exists():
                return str(local)
            continue

        if path.exists():
            return str(path)

    return None


@lru_cache(maxsize=1)
def regular_path() -> str | None:
    path = _resolve(REGULAR_CANDIDATES)
    if path is None:
        log.warning(
            "TTF shrift topilmadi — Pillow'ning ichki shrifti ishlatiladi. "
            "Chiroyliroq natija uchun assets/fonts/ ga DejaVuSans.ttf qo'ying."
        )
    return path


@lru_cache(maxsize=1)
def bold_path() -> str | None:
    return _resolve(BOLD_CANDIDATES) or regular_path()


@lru_cache(maxsize=1)
def mono_path() -> str | None:
    return _resolve(MONO_CANDIDATES) or regular_path()


@lru_cache(maxsize=1)
def mono_bold_path() -> str | None:
    return _resolve(MONO_BOLD_CANDIDATES) or mono_path()


@lru_cache(maxsize=128)
def font(size: int, *, bold: bool = False, mono: bool = False):
    """
    Berilgan o'lchamdagi shriftni qaytaradi.

    Natija keshlanadi — bir xil o'lcham qayta-qayta yuklanmaydi.
    """
    if mono:
        path = mono_bold_path() if bold else mono_path()
    else:
        path = bold_path() if bold else regular_path()

    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError as error:
            log.warning("Shriftni yuklab bo'lmadi (%s): %s", path, error)

    #  Oxirgi zaxira — Pillow'ning ichki shrifti
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def available() -> bool:
    """Haqiqiy TTF shrift mavjudmi (diagnostika uchun)."""
    return regular_path() is not None
