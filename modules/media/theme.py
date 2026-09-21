"""
Rasm chizish uchun umumiy uslub: ranglar, gradient, shakllar.

Rang sxemasi — to'q ko'k va oltin. Bu Telegram'ning to'q mavzusida
yaxshi ko'rinadi va "premium" hissini beradi: sertifikat, diplom,
nishon — hammasi shu palitrada.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

#  --- Asosiy palitra ---
NAVY_DARK = (10, 22, 48)        # eng to'q — burchaklar
NAVY = (16, 36, 74)             # asosiy fon
NAVY_LIGHT = (26, 54, 104)      # yorug' joy
GOLD = (212, 175, 55)           # oltin — sarlavha, ramka
GOLD_SOFT = (180, 148, 48)      # so'nik oltin
WHITE = (255, 255, 255)
CREAM = (240, 238, 230)
MUTED = (150, 165, 190)         # ikkinchi darajali matn

#  --- Semantik ranglar ---
GREEN = (76, 187, 122)          # to'g'ri, o'tdi
RED = (226, 96, 88)             # xato
ORANGE = (232, 156, 76)         # ogohlantirish
GREY = (110, 125, 150)          # javobsiz

#  --- Baho ranglari ---
GRADE_COLORS: dict[str, tuple[int, int, int]] = {
    "A+": (255, 215, 0),
    "A": (120, 200, 140),
    "B": (110, 180, 220),
    "C": (232, 180, 90),
    "D": (232, 140, 90),
    "F": (226, 96, 88),
}


def grade_color(grade: str | None) -> tuple[int, int, int]:
    return GRADE_COLORS.get((grade or "").upper(), MUTED)


def score_color(percentage: float, pass_score: int = 60) -> tuple[int, int, int]:
    """Foizga qarab rang: yashil / sariq / qizil."""
    if percentage >= 85:
        return GREEN
    if percentage >= pass_score:
        return (150, 200, 120)
    if percentage >= pass_score * 0.6:
        return ORANGE
    return RED


# ----------------------------------------------------------------------
#  Fon
# ----------------------------------------------------------------------

def gradient_background(
    width: int,
    height: int,
    *,
    top: tuple[int, int, int] = NAVY_LIGHT,
    bottom: tuple[int, int, int] = NAVY_DARK,
) -> Image.Image:
    """
    Vertikal gradient fon.

    Har bir qator uchun rang oralig'i chiziqli hisoblanadi. Bu Pillow'da
    gradient yasashning eng tez usuli — piksel-piksel emas, qator-qator.
    """
    image = Image.new("RGB", (width, height), bottom)
    draw = ImageDraw.Draw(image)

    for y in range(height):
        ratio = y / max(1, height - 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * ratio),
            int(top[1] + (bottom[1] - top[1]) * ratio),
            int(top[2] + (bottom[2] - top[2]) * ratio),
        )
        draw.line([(0, y), (width, y)], fill=color)

    return image


def radial_glow(
    image: Image.Image,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    *,
    strength: float = 0.25,
) -> Image.Image:
    """
    Yumshoq yorug'lik dog'i qo'shadi.

    Kartochkaning yuqori qismiga qo'yiladi — tekis fonni "tirik" qiladi.
    """
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    steps = 24
    for index in range(steps, 0, -1):
        ratio = index / steps
        current = int(radius * ratio)
        alpha = int(255 * strength * (1 - ratio) ** 2)
        draw.ellipse(
            [
                center[0] - current, center[1] - current,
                center[0] + current, center[1] + current,
            ],
            fill=(*color, alpha),
        )

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


# ----------------------------------------------------------------------
#  Shakllar
# ----------------------------------------------------------------------

def rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    radius: int = 18,
    fill: tuple[int, int, int] | None = None,
    outline: tuple[int, int, int] | None = None,
    width: int = 2,
) -> None:
    """Yumaloq burchakli panel."""
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def double_frame(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    *,
    margin: int = 26,
    gap: int = 10,
    color: tuple[int, int, int] = GOLD,
) -> None:
    """
    Ikki qatorli ramka — sertifikat uslubi.

    Tashqi chiziq qalin, ichkisi ingichka. Bu klassik diplom ko'rinishi.
    """
    width, height = size

    draw.rectangle(
        [margin, margin, width - margin, height - margin],
        outline=color,
        width=3,
    )
    draw.rectangle(
        [margin + gap, margin + gap, width - margin - gap, height - margin - gap],
        outline=(*color[:3],) if len(color) == 3 else color,
        width=1,
    )


def corner_marks(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    *,
    margin: int = 26,
    length: int = 46,
    color: tuple[int, int, int] = GOLD,
    width: int = 4,
) -> None:
    """Burchak belgilari — ramkani "tugallangan" qiladi."""
    w, h = size
    m = margin

    #  Yuqori chap
    draw.line([(m, m + length), (m, m), (m + length, m)], fill=color, width=width)
    #  Yuqori o'ng
    draw.line([(w - m - length, m), (w - m, m), (w - m, m + length)], fill=color, width=width)
    #  Pastki chap
    draw.line([(m, h - m - length), (m, h - m), (m + length, h - m)], fill=color, width=width)
    #  Pastki o'ng
    draw.line(
        [(w - m - length, h - m), (w - m, h - m), (w - m, h - m - length)],
        fill=color, width=width,
    )


# ----------------------------------------------------------------------
#  Matn
# ----------------------------------------------------------------------

def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    """Matn o'lchami (kenglik, balandlik)."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    *,
    y: int,
    width: int,
    fill: tuple[int, int, int] = WHITE,
    spacing: int = 0,
) -> int:
    """
    Matnni gorizontal markazga joylashtiradi.

    `spacing` — harflar orasidagi qo'shimcha masofa. Sarlavhalarda
    harflarni yoyish "premium" ko'rinish beradi.

    Returns:
        Matn pastki chegarasi (keyingi element uchun).
    """
    if spacing <= 0:
        text_width, text_height = text_size(draw, text, font)
        draw.text(((width - text_width) // 2, y), text, font=font, fill=fill)
        return y + text_height

    #  Harflarni birma-bir chizamiz
    widths = [text_size(draw, char, font)[0] for char in text]
    total = sum(widths) + spacing * max(0, len(text) - 1)

    x = (width - total) // 2
    height = 0

    for char, char_width in zip(text, widths):
        draw.text((x, y), char, font=font, fill=fill)
        height = max(height, text_size(draw, char, font)[1])
        x += char_width + spacing

    return y + height


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    *,
    size: int,
    bold: bool = False,
    min_size: int = 14,
):
    """
    Matn kengligiga sig'adigan eng katta shriftni tanlaydi.

    Uzun test nomlari kartochkadan chiqib ketmasligi uchun kerak.
    """
    from modules.media import fonts

    current = size
    while current > min_size:
        candidate = fonts.font(current, bold=bold)
        if text_size(draw, text, candidate)[0] <= max_width:
            return candidate
        current -= 2

    return fonts.font(min_size, bold=bold)


def truncate(text: str, limit: int) -> str:
    """Uzun matnni kesadi."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"
