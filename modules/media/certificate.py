"""
Sertifikat — QR kod bilan tekshiriladigan.

MUHIM: sertifikat **yakun emas, keyingi qadamga taklif**. Shuning uchun
matnlar natijaga qarab o'zgaradi va har biri o'quvchini davom etishga
undaydi. "Sertifikat berildi" degan quruq gap hech kimni qiziqtirmaydi.

QR kod `t.me/bot?start=cert_<seriya>` havolasiga olib boradi — istalgan
odam skanerlab, sertifikat rostdan berilganini tekshira oladi.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from core.config import settings
from core.datetime_utils import fmt_date_uz
from core.logging import get_logger
from modules.media import fonts, theme
from modules.media.qr import make_qr_rounded

log = get_logger(__name__)

#  Gorizontal — diplom odatda shunday bo'ladi
WIDTH = 1748
HEIGHT = 1240


#  Natijaga qarab motivatsion matn.
#  (minimal foiz, sarlavha, matn)
MOTIVATION: tuple[tuple[int, str, str], ...] = (
    (95, "MUKAMMAL NATIJA",
     "Siz bu mavzuni to'liq egallagansiz. Endi murakkabroq\n"
     "testlarni sinab ko'ring — sizga osonlik qilyapti."),
    (85, "AJOYIB NATIJA",
     "Yana bir oz — va cho'qqi sizniki bo'ladi.\n"
     "Xatolaringizni ko'rib chiqsangiz, keyingi safar 100%."),
    (70, "YAXSHI NATIJA",
     "Mustahkam bilim. Xatolaringiz ustida ishlasangiz,\n"
     "keyingi testda 90% dan oshasiz."),
    (60, "SIZ O'TDINGIZ",
     "Boshlanish yaxshi. Endi xatolaringizni ko'rib chiqing\n"
     "va shu mavzuni yana bir bor sinab ko'ring."),
    (0, "HARAKATINGIZ UCHUN",
     "Har bir urinish — bilim. Xatolaringizni o'rganing\n"
     "va qaytadan urinib ko'ring, natija albatta yaxshilanadi."),
)


def motivation_for(percentage: float) -> tuple[str, str]:
    """Foizga mos sarlavha va matn."""
    for minimum, title, text in MOTIVATION:
        if percentage >= minimum:
            return title, text
    return MOTIVATION[-1][1], MOTIVATION[-1][2]


@dataclass(slots=True)
class CertificateData:
    """Sertifikat uchun ma'lumot."""

    serial: str
    holder_name: str
    test_title: str
    percentage: float
    score: int
    max_score: int
    grade: str
    rank: int
    participants: int
    issued_at: object            # datetime
    verify_link: str = ""


def render(data: CertificateData) -> bytes:
    """Sertifikatni chizadi va PNG baytlarini qaytaradi."""
    image = theme.gradient_background(
        WIDTH, HEIGHT, top=theme.NAVY_LIGHT, bottom=theme.NAVY_DARK
    )
    image = theme.radial_glow(
        image, center=(WIDTH // 2, 260), radius=760,
        color=theme.NAVY_LIGHT, strength=0.28,
    )

    draw = ImageDraw.Draw(image)

    theme.double_frame(draw, (WIDTH, HEIGHT), margin=40, gap=12)
    theme.corner_marks(draw, (WIDTH, HEIGHT), margin=40, length=76, width=5)

    cursor = _draw_title(draw)
    cursor = _draw_holder(draw, data, top=cursor)
    cursor = _draw_test(draw, data, top=cursor)
    cursor = _draw_scores(draw, data, top=cursor)
    _draw_motivation(draw, data, top=cursor)
    _draw_footer(image, draw, data)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ----------------------------------------------------------------------

def _draw_title(draw: ImageDraw.ImageDraw) -> int:
    theme.centered_text(
        draw, settings.app.name.upper(), fonts.font(30, bold=True),
        y=104, width=WIDTH, fill=theme.MUTED, spacing=10,
    )

    theme.centered_text(
        draw, "SERTIFIKAT", fonts.font(104, bold=True),
        y=158, width=WIDTH, fill=theme.GOLD, spacing=16,
    )

    #  Bezak: chiziq — romb — chiziq
    y = 300
    draw.line([(WIDTH // 2 - 300, y), (WIDTH // 2 - 40, y)],
              fill=theme.GOLD_SOFT, width=2)
    draw.line([(WIDTH // 2 + 40, y), (WIDTH // 2 + 300, y)],
              fill=theme.GOLD_SOFT, width=2)
    draw.polygon(
        [(WIDTH // 2, y - 12), (WIDTH // 2 + 14, y), (WIDTH // 2, y + 12), (WIDTH // 2 - 14, y)],
        fill=theme.GOLD,
    )

    return 330


def _draw_holder(draw: ImageDraw.ImageDraw, data: CertificateData, *, top: int) -> int:
    theme.centered_text(
        draw, "USHBU SERTIFIKAT BERILDI", fonts.font(26),
        y=top, width=WIDTH, fill=theme.MUTED, spacing=4,
    )

    name = theme.truncate(data.holder_name, 40)
    name_font = theme.fit_text(draw, name, WIDTH - 420, size=82, bold=True)
    theme.centered_text(draw, name, name_font, y=top + 52, width=WIDTH, fill=theme.WHITE)

    #  Ism ostidagi chiziq
    line_y = top + 154
    draw.line([(WIDTH // 2 - 380, line_y), (WIDTH // 2 + 380, line_y)],
              fill=theme.GOLD_SOFT, width=2)

    return line_y + 30


def _draw_test(draw: ImageDraw.ImageDraw, data: CertificateData, *, top: int) -> int:
    theme.centered_text(
        draw, "quyidagi test bo'yicha:", fonts.font(26),
        y=top, width=WIDTH, fill=theme.MUTED,
    )

    title = f"«{theme.truncate(data.test_title, 44)}»"
    title_font = theme.fit_text(draw, title, WIDTH - 420, size=44, bold=True)
    theme.centered_text(draw, title, title_font, y=top + 44, width=WIDTH, fill=theme.CREAM)

    return top + 118


def _draw_scores(draw: ImageDraw.ImageDraw, data: CertificateData, *, top: int) -> int:
    """Natija bloklari."""
    blocks: list[tuple[str, str, tuple[int, int, int]]] = [
        ("NATIJA", f"{data.percentage:g}%", theme.score_color(data.percentage)),
        ("BALL", f"{data.score}/{data.max_score}", theme.WHITE),
        ("BAHO", data.grade, theme.grade_color(data.grade)),
    ]

    if data.participants:
        blocks.append(("REYTING", f"{data.rank}/{data.participants}", theme.CREAM))

    gap = 26
    panel_width = 268
    panel_height = 132
    total = len(blocks) * panel_width + (len(blocks) - 1) * gap
    x = (WIDTH - total) // 2

    label_font = fonts.font(21, bold=True)
    value_font = fonts.font(46, bold=True)

    for label, value, color in blocks:
        theme.rounded_panel(
            draw, (x, top, x + panel_width, top + panel_height),
            radius=18, fill=theme.NAVY_LIGHT, outline=theme.NAVY, width=1,
        )

        label_width, _ = theme.text_size(draw, label, label_font)
        draw.text((x + (panel_width - label_width) // 2, top + 22),
                  label, font=label_font, fill=theme.MUTED)

        value_width, _ = theme.text_size(draw, value, value_font)
        draw.text((x + (panel_width - value_width) // 2, top + 60),
                  value, font=value_font, fill=color)

        x += panel_width + gap

    return top + panel_height + 34


def _draw_motivation(draw: ImageDraw.ImageDraw, data: CertificateData, *, top: int) -> None:
    """
    Natijaga mos motivatsion matn.

    Sertifikatning eng muhim qismi: o'quvchi buni o'qib, keyingi
    testni yechishga qiziqishi kerak.
    """
    title, text = motivation_for(data.percentage)

    theme.centered_text(
        draw, title, fonts.font(30, bold=True),
        y=top, width=WIDTH, fill=theme.GOLD, spacing=4,
    )

    y = top + 48
    for line in text.split("\n"):
        theme.centered_text(
            draw, line, fonts.font(24),
            y=y, width=WIDTH, fill=theme.MUTED,
        )
        y += 34


def _draw_footer(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    data: CertificateData,
) -> None:
    """
    Muhr, sana, seriya raqami va QR.

    JOYLASHUV QOIDASI
    -----------------
    Ichki ramka `HEIGHT - 52` da turadi. Markazdagi ustun (sana →
    chiziq → seriya → izoh) undan YUQORIDA tugashi shart, aks holda
    ramka chizig'i matn ustidan o'tib ketadi.

    Shuning uchun elementlar sobit siljishlar bilan emas, ketma-ket
    hisoblanadi.
    """
    inner_frame_top = HEIGHT - 52
    block_top = HEIGHT - 290

    #  --- Muhr (chapda) ---
    _draw_seal(draw, center=(238, block_top + 96), radius=86, grade=data.grade)

    #  --- QR (o'ngda) ---
    link = data.verify_link or settings.bot.deep_link(f"cert_{data.serial}")
    qr_size = 168
    qr_left = WIDTH - 238 - qr_size // 2

    try:
        qr_image = make_qr_rounded(link, size=qr_size)
        image.paste(qr_image, (qr_left, block_top + 10))
    except Exception as error:
        #  QR chizilmasa sertifikat baribir berilsin
        log.warning("Sertifikat QR kodi chizilmadi: %s", error)

    scan_font = fonts.font(17)
    scan_text = "Tekshirish uchun skanerlang"
    scan_width, _ = theme.text_size(draw, scan_text, scan_font)
    draw.text(
        (qr_left + (qr_size - scan_width) // 2, block_top + qr_size + 20),
        scan_text, font=scan_font, fill=theme.MUTED,
    )

    #  --- Markaziy ustun ---
    y = block_top + 34

    y = theme.centered_text(
        draw, "BERILGAN SANA", fonts.font(21, bold=True),
        y=y, width=WIDTH, fill=theme.MUTED, spacing=3,
    ) + 12

    y = theme.centered_text(
        draw, fmt_date_uz(data.issued_at), fonts.font(32, bold=True),
        y=y, width=WIDTH, fill=theme.WHITE,
    ) + 16

    draw.line([(WIDTH // 2 - 190, y), (WIDTH // 2 + 190, y)],
              fill=theme.GOLD_SOFT, width=2)
    y += 18

    y = theme.centered_text(
        draw, f"№ {data.serial}", fonts.font(26, bold=True),
        y=y, width=WIDTH, fill=theme.GOLD,
    ) + 10

    note_font = fonts.font(18)
    note = "Ushbu sertifikat avtomatik shakllantirilgan va QR kod orqali tekshiriladi"
    _, note_height = theme.text_size(draw, note, note_font)

    #  Ramkaga tegib ketmasin
    y = min(y, inner_frame_top - note_height - 14)
    theme.centered_text(draw, note, note_font, y=y, width=WIDTH, fill=theme.MUTED)


def _draw_seal(
    draw: ImageDraw.ImageDraw,
    *,
    center: tuple[int, int],
    radius: int,
    grade: str,
) -> None:
    """Nurli muhr — bahoni ko'rsatadi."""
    import math

    x, y = center

    #  Nurlar
    for index in range(48):
        angle = math.radians(index * 360 / 48)
        inner = radius + 6
        outer = radius + (20 if index % 2 == 0 else 12)
        draw.line(
            [
                (x + inner * math.cos(angle), y + inner * math.sin(angle)),
                (x + outer * math.cos(angle), y + outer * math.sin(angle)),
            ],
            fill=theme.GOLD_SOFT, width=2,
        )

    draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                 outline=theme.GOLD, width=4)
    draw.ellipse([x - radius + 12, y - radius + 12, x + radius - 12, y + radius - 12],
                 outline=theme.GOLD_SOFT, width=1)

    grade_font = fonts.font(48, bold=True)
    grade_width, grade_height = theme.text_size(draw, grade, grade_font)
    draw.text((x - grade_width // 2, y - grade_height // 2 - 14),
              grade, font=grade_font, fill=theme.grade_color(grade))

    #  Yozuv ichki doiraga sig'ishi kerak — shrift o'lchamini moslaymiz
    label = "TASDIQLANDI"
    inner_width = (radius - 18) * 2
    small_font = theme.fit_text(draw, label, inner_width, size=16, bold=True, min_size=11)
    label_width, _ = theme.text_size(draw, label, small_font)
    draw.text((x - label_width // 2, y + 26), label, font=small_font, fill=theme.GOLD_SOFT)


def filename(data: CertificateData) -> str:
    return f"sertifikat_{data.serial}.png"
