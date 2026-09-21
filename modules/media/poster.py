"""
Test posteri — guruhga tashlanadigan reklama.

O'qituvchi testni e'lon qilganda bot poster chizadi. U guruhga
uzatilganda oddiy xabar emas, **e'lon** kabi ko'rinadi: katta test
raqami, savollar soni, muallif nomi va QR kod.

Ostidagi tugma `t.me/bot?start=t12` havolasiga olib boradi — o'quvchi
raqam terib o'tirmaydi, bitta bosishda test ochiladi.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from core.config import settings
from core.logging import get_logger
from modules.media import fonts, theme
from modules.media.qr import make_qr

log = get_logger(__name__)

WIDTH = 1080

#  Balandlik kontentga moslangan: 1350 da o'rtada katta bo'sh joy
#  qolib ketardi. Hozirgi nisbat ham Telegram uchun qulay.
HEIGHT = 1180


@dataclass(slots=True)
class PosterData:
    """Poster uchun ma'lumot."""

    test_title: str
    test_number: int
    questions_count: int
    author_name: str

    category: str | None = None
    time_limit_min: int = 0
    pass_score: int = 60
    deep_link: str = ""


def render(data: PosterData) -> bytes:
    """Posterni chizadi va PNG baytlarini qaytaradi."""
    image = theme.gradient_background(WIDTH, HEIGHT)
    image = theme.radial_glow(
        image, center=(WIDTH // 2, 380), radius=620,
        color=theme.NAVY_LIGHT, strength=0.35,
    )

    draw = ImageDraw.Draw(image)

    theme.double_frame(draw, (WIDTH, HEIGHT), margin=30, gap=10)
    theme.corner_marks(draw, (WIDTH, HEIGHT), margin=30, length=56)

    cursor = _draw_head(draw, data)
    cursor = _draw_number(draw, data, top=cursor)
    cursor = _draw_details(draw, data, top=cursor)
    _draw_call_to_action(image, draw, data, top=cursor)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ----------------------------------------------------------------------

def _draw_head(draw: ImageDraw.ImageDraw, data: PosterData) -> int:
    """Platforma, kategoriya va test nomi."""
    theme.centered_text(
        draw, settings.app.name.upper(), fonts.font(28, bold=True),
        y=86, width=WIDTH, fill=theme.MUTED, spacing=7,
    )

    y = 150

    if data.category:
        theme.centered_text(
            draw, data.category.upper(), fonts.font(30, bold=True),
            y=y, width=WIDTH, fill=theme.GOLD, spacing=3,
        )
        y += 56

    title = theme.truncate(data.test_title, 40)
    title_font = theme.fit_text(draw, title, WIDTH - 180, size=62, bold=True)
    theme.centered_text(draw, title, title_font, y=y, width=WIDTH, fill=theme.WHITE)

    return y + 100


def _draw_number(draw: ImageDraw.ImageDraw, data: PosterData, *, top: int) -> int:
    """
    Katta test raqami — posterning markazi.

    Bu eng muhim ma'lumot: o'quvchi botga aynan shu raqamni yozadi.
    """
    theme.centered_text(
        draw, "TEST RAQAMI", fonts.font(24, bold=True),
        y=top, width=WIDTH, fill=theme.MUTED, spacing=5,
    )

    box_top = top + 46
    box_height = 210
    box_width = 380
    left = (WIDTH - box_width) // 2

    theme.rounded_panel(
        draw, (left, box_top, left + box_width, box_top + box_height),
        radius=28, fill=theme.NAVY_LIGHT, outline=theme.GOLD, width=3,
    )

    number = str(data.test_number)
    number_font = theme.fit_text(draw, number, box_width - 80, size=140, bold=True)
    width, height = theme.text_size(draw, number, number_font)
    draw.text(
        (WIDTH // 2 - width // 2, box_top + (box_height - height) // 2 - 12),
        number, font=number_font, fill=theme.GOLD,
    )

    return box_top + box_height + 46


def _draw_details(draw: ImageDraw.ImageDraw, data: PosterData, *, top: int) -> int:
    """Savollar soni, vaqt, o'tish balli, muallif."""
    rows: list[tuple[str, str]] = [
        ("SAVOLLAR", f"{data.questions_count} ta"),
    ]

    if data.time_limit_min:
        rows.append(("VAQT", f"{data.time_limit_min} daqiqa"))

    rows.append(("O'TISH BALLI", f"{data.pass_score}%"))

    gap = 18
    panel_width = (WIDTH - 200 - gap * (len(rows) - 1)) // len(rows)
    panel_height = 104
    x = 100

    label_font = fonts.font(19, bold=True)
    value_font = fonts.font(32, bold=True)

    for label, value in rows:
        theme.rounded_panel(
            draw, (x, top, x + panel_width, top + panel_height),
            radius=16, fill=theme.NAVY_LIGHT,
        )

        label_width, _ = theme.text_size(draw, label, label_font)
        draw.text((x + (panel_width - label_width) // 2, top + 20),
                  label, font=label_font, fill=theme.MUTED)

        value_width, _ = theme.text_size(draw, value, value_font)
        draw.text((x + (panel_width - value_width) // 2, top + 50),
                  value, font=value_font, fill=theme.WHITE)

        x += panel_width + gap

    y = top + panel_height + 34

    author = theme.truncate(data.author_name, 36)
    theme.centered_text(
        draw, author, fonts.font(30, bold=True),
        y=y, width=WIDTH, fill=theme.CREAM,
    )
    theme.centered_text(
        draw, "test muallifi", fonts.font(21),
        y=y + 42, width=WIDTH, fill=theme.MUTED,
    )

    return y + 86


def _draw_call_to_action(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    data: PosterData,
    *,
    top: int,
) -> None:
    """
    Pastki blok: QR kod va qanday qatnashish.

    `top` — yuqoridagi kontent qayerda tugagani. Blok undan pastda,
    lekin ramkaga tegmasdan joylashadi.
    """
    baseline = max(top + 20, HEIGHT - 300)

    draw.line([(140, baseline), (WIDTH - 140, baseline)],
              fill=theme.NAVY_LIGHT, width=2)

    #  --- QR kod ---
    link = data.deep_link or settings.bot.deep_link(f"t{data.test_number}")
    qr_size = 190

    try:
        qr_image = make_qr(link, size=qr_size)
        image.paste(qr_image, (140, baseline + 40))
    except Exception as error:
        #  QR chizilmasa poster baribir yuborilsin
        log.warning("QR kod chizilmadi: %s", error)

    #  --- Ko'rsatma ---
    text_left = 140 + qr_size + 44
    y = baseline + 52

    draw.text((text_left, y), "QATNASHISH UCHUN",
              font=fonts.font(22, bold=True), fill=theme.GOLD)

    draw.text((text_left, y + 44), f"@{settings.bot.username}",
              font=fonts.font(30, bold=True), fill=theme.WHITE)

    draw.text((text_left, y + 90), "botiga kiring va",
              font=fonts.font(22), fill=theme.MUTED)

    draw.text((text_left, y + 124), f"{data.test_number}",
              font=fonts.font(44, bold=True), fill=theme.GOLD)

    number_width, _ = theme.text_size(draw, str(data.test_number),
                                      fonts.font(44, bold=True))
    draw.text((text_left + number_width + 14, y + 136), "sonini yuboring",
              font=fonts.font(22), fill=theme.MUTED)


def filename(data: PosterData) -> str:
    return f"test_{data.test_number}.png"
