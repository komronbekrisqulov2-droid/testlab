"""
Natija kartochkasi — ulashiladigan PNG.

Nega rasm? Matnli natijani hech kim ulashmaydi. Rasm esa story'ga
tashlanadi, do'stga yuboriladi — **har bir ulashish bepul reklama**.

Kartochkada o'quvchining OLDINGI natijalari ham bor: u o'z o'sishini
ko'radi. Bu qaytishning eng kuchli sababi.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import ImageDraw

from core.config import settings
from core.datetime_utils import fmt_date, utcnow
from core.logging import get_logger
from modules.media import fonts, theme

log = get_logger(__name__)

WIDTH = 1080
HEIGHT = 1080  # kvadrat — story va postga bir xil mos keladi


@dataclass(slots=True)
class ResultCardData:
    """Kartochka uchun kerak bo'ladigan hamma narsa."""

    student_name: str
    test_title: str
    test_number: int
    percentage: float
    correct: int
    total: int
    wrong: int
    skipped: int
    grade: str
    rank: int
    participants: int
    passed: bool
    pass_score: int = 60

    #  Oldingi natijalar (eng eskisidan eng yangisiga), foizda.
    #  Oxirgisi — shu urinish.
    history: tuple[float, ...] = ()

    #  Ketma-ket faol kunlar
    streak: int = 0


def render(data: ResultCardData) -> bytes:
    """Kartochkani chizadi va PNG baytlarini qaytaradi."""
    image = theme.gradient_background(WIDTH, HEIGHT)
    image = theme.radial_glow(
        image, center=(WIDTH // 2, 210), radius=520,
        color=theme.NAVY_LIGHT, strength=0.30,
    )

    draw = ImageDraw.Draw(image)

    theme.double_frame(draw, (WIDTH, HEIGHT), margin=28, gap=9)
    theme.corner_marks(draw, (WIDTH, HEIGHT), margin=28, length=50)

    cursor = _draw_header(draw, data)
    cursor = _draw_score(draw, data, top=cursor)
    cursor = _draw_stats(draw, data, top=cursor)
    cursor = _draw_history(draw, data, top=cursor)
    _draw_footer(draw, data, top=cursor)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ----------------------------------------------------------------------
#  Bloklar
# ----------------------------------------------------------------------

def _draw_header(draw: ImageDraw.ImageDraw, data: ResultCardData) -> int:
    """Platforma nomi, test nomi, o'quvchi."""
    theme.centered_text(
        draw, settings.app.name.upper(), fonts.font(26, bold=True),
        y=72, width=WIDTH, fill=theme.MUTED, spacing=6,
    )

    title = theme.truncate(data.test_title, 44)
    title_font = theme.fit_text(draw, title, WIDTH - 200, size=52, bold=True)
    theme.centered_text(draw, title, title_font, y=124, width=WIDTH, fill=theme.WHITE)

    theme.centered_text(
        draw, f"Test №{data.test_number}", fonts.font(26),
        y=192, width=WIDTH, fill=theme.GOLD_SOFT,
    )

    #  Ajratuvchi
    draw.line([(WIDTH // 2 - 160, 240), (WIDTH // 2 + 160, 240)],
              fill=theme.GOLD_SOFT, width=2)

    name = theme.truncate(data.student_name, 34)
    name_font = theme.fit_text(draw, name, WIDTH - 240, size=44, bold=True)
    theme.centered_text(draw, name, name_font, y=266, width=WIDTH, fill=theme.CREAM)

    return 340


def _draw_score(draw: ImageDraw.ImageDraw, data: ResultCardData, *, top: int) -> int:
    """
    Katta foiz va halqa.

    Foiz halqa MARKAZIDA, baho esa halqa OSTIDA — ilgari ikkalasi
    bir-biriga tegib turardi.
    """
    color = theme.score_color(data.percentage, data.pass_score)

    center_x, center_y = WIDTH // 2, top + 122
    radius = 112

    draw.ellipse(
        [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
        outline=theme.NAVY_LIGHT, width=15,
    )

    #  To'ldirilgan yoy — natija ulushi
    sweep = 360 * min(100.0, max(0.0, data.percentage)) / 100
    if sweep > 0:
        draw.arc(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            start=-90, end=-90 + sweep, fill=color, width=15,
        )

    #  Foiz — halqaning aniq markazida
    percent_text = f"{data.percentage:g}%"
    percent_font = theme.fit_text(
        draw, percent_text, radius * 2 - 44, size=78, bold=True, min_size=44,
    )
    width, height = theme.text_size(draw, percent_text, percent_font)
    draw.text(
        (center_x - width // 2, center_y - height // 2 - 6),
        percent_text, font=percent_font, fill=color,
    )

    #  Baho — halqa ostidagi alohida nishon
    grade_font = fonts.font(28, bold=True)
    grade_width, grade_height = theme.text_size(draw, data.grade, grade_font)
    badge_width = max(96, grade_width + 48)
    badge_top = center_y + radius + 6

    theme.rounded_panel(
        draw,
        (center_x - badge_width // 2, badge_top,
         center_x + badge_width // 2, badge_top + 46),
        radius=14, fill=theme.NAVY_LIGHT,
    )
    draw.text(
        (center_x - grade_width // 2, badge_top + (46 - grade_height) // 2 - 4),
        data.grade, font=grade_font, fill=theme.grade_color(data.grade),
    )

    return badge_top + 46 + 26


def _draw_stats(draw: ImageDraw.ImageDraw, data: ResultCardData, *, top: int) -> int:
    """To'g'ri / xato / javobsiz bloklari."""
    blocks: list[tuple[str, str, tuple[int, int, int]]] = [
        ("TO'G'RI", str(data.correct), theme.GREEN),
        ("XATO", str(data.wrong), theme.RED),
    ]
    if data.skipped:
        blocks.append(("JAVOBSIZ", str(data.skipped), theme.GREY))
    blocks.append(("BALL", f"{data.correct}/{data.total}", theme.WHITE))

    count = len(blocks)
    gap = 20
    panel_width = (WIDTH - 200 - gap * (count - 1)) // count
    panel_height = 108
    x = 100

    label_font = fonts.font(19, bold=True)
    value_font = fonts.font(38, bold=True)

    for label, value, color in blocks:
        theme.rounded_panel(
            draw, (x, top, x + panel_width, top + panel_height),
            radius=16, fill=theme.NAVY_LIGHT, outline=None,
        )

        label_width, _ = theme.text_size(draw, label, label_font)
        draw.text(
            (x + (panel_width - label_width) // 2, top + 18),
            label, font=label_font, fill=theme.MUTED,
        )

        value_width, _ = theme.text_size(draw, value, value_font)
        draw.text(
            (x + (panel_width - value_width) // 2, top + 48),
            value, font=value_font, fill=color,
        )

        x += panel_width + gap

    return top + panel_height + 30


def _draw_history(draw: ImageDraw.ImageDraw, data: ResultCardData, *, top: int) -> int:
    """
    O'sish grafigi — oldingi natijalar.

    Ustunlar ko'rinishida. Oxirgisi (shu urinish) ajratib ko'rsatiladi.
    Tarix bo'lmasa blok umuman chizilmaydi.
    """
    history = [value for value in data.history if value is not None]

    if len(history) < 2:
        return top

    history = history[-6:]

    theme.centered_text(
        draw, "O'SISHINGIZ", fonts.font(20, bold=True),
        y=top, width=WIDTH, fill=theme.MUTED, spacing=4,
    )

    chart_top = top + 32
    chart_height = 100
    bar_width = 76
    gap = 20
    total_width = len(history) * bar_width + (len(history) - 1) * gap
    x = (WIDTH - total_width) // 2

    #  MASSHTAB: 0–100 emas, min–max oralig'ida chizamiz.
    #
    #  45% dan 92% gacha o'sish 0–100 shkalasida deyarli sezilmaydi —
    #  ustunlar bir xil ko'rinadi va grafikning ma'nosi yo'qoladi.
    #  Diapazonga moslash farqni ko'rsatadi.
    lowest = min(history)
    highest = max(history)
    span = max(12.0, highest - lowest)      # juda tor bo'lsa ham tekislanmasin
    floor = max(0.0, lowest - span * 0.25)

    value_font = fonts.font(17, bold=True)
    baseline = chart_top + chart_height

    for index, value in enumerate(history):
        is_last = index == len(history) - 1

        ratio = (value - floor) / max(1e-6, (highest - floor))
        height = max(14, int(chart_height * (0.18 + 0.82 * ratio)))

        color = (
            theme.score_color(value, data.pass_score) if is_last
            else theme.NAVY_LIGHT
        )

        theme.rounded_panel(
            draw, (x, baseline - height, x + bar_width, baseline),
            radius=8, fill=color,
        )

        text = f"{value:g}"
        text_width, _ = theme.text_size(draw, text, value_font)
        draw.text(
            (x + (bar_width - text_width) // 2, baseline + 8),
            text, font=value_font,
            fill=theme.WHITE if is_last else theme.MUTED,
        )

        x += bar_width + gap

    return baseline + 36


def _draw_footer(draw: ImageDraw.ImageDraw, data: ResultCardData, *, top: int) -> None:
    """
    Reyting, seriya, sana va bot manzili.

    `top` — yuqoridagi kontent qayerda tugagani. Xulosa qatori undan
    PASTDA chiziladi, aks holda o'sish grafigining ustiga tushib
    qolardi.

    Reyting va seriya BITTA qatorda birlashtiriladi — ikki alohida
    qator uchun joy yetmaydi va baribir bir xil ma'noni beradi.
    """
    divider_y = HEIGHT - 76

    #  --- Pastki qator: sana va bot ---
    draw.line([(120, divider_y), (WIDTH - 120, divider_y)],
              fill=theme.NAVY_LIGHT, width=2)

    small = fonts.font(20)
    draw.text((120, divider_y + 16), fmt_date(utcnow()), font=small, fill=theme.MUTED)

    bot_text = f"@{settings.bot.username}"
    bot_width, _ = theme.text_size(draw, bot_text, small)
    draw.text((WIDTH - 120 - bot_width, divider_y + 16), bot_text,
              font=small, fill=theme.GOLD_SOFT)

    #  --- Xulosa qatori ---
    parts: list[str] = []

    if data.participants:
        medal = {1: "1-O'RIN", 2: "2-O'RIN", 3: "3-O'RIN"}.get(
            data.rank, f"{data.rank}-O'RIN"
        )
        parts.append(f"{medal} · {data.participants} ISHTIROKCHIDAN")

    if data.streak >= 2:
        parts.append(f"{data.streak} KUN KETMA-KET")

    if not parts:
        return

    summary = "   ·   ".join(parts)
    summary_font = theme.fit_text(
        draw, summary, WIDTH - 200, size=24, bold=True, min_size=16,
    )
    _, summary_height = theme.text_size(draw, summary, summary_font)

    #  Kontentdan keyin, lekin chiziqqa tegmasdan
    y = max(top + 6, divider_y - summary_height - 20)

    theme.centered_text(
        draw, summary, summary_font, y=y, width=WIDTH,
        fill=theme.GOLD if data.rank <= 3 else theme.MUTED,
    )


def filename(data: ResultCardData) -> str:
    """Yuboriladigan fayl nomi."""
    return f"natija_{data.test_number}_{int(data.percentage)}.png"
