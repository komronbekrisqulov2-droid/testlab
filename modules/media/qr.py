"""
QR kod yasash.

Ikki joyda ishlatiladi:
    * poster    — testga tez kirish havolasi
    * sertifikat — haqiqiyligini tekshirish havolasi

Sertifikatdagi QR eng muhimi: uni skanerlagan odam botga tushadi va
sertifikat rostdan berilganini ko'radi. Ya'ni soxta sertifikatni
ajratib bo'ladi.
"""

from __future__ import annotations

import qrcode
from PIL import Image
from qrcode.constants import ERROR_CORRECT_M

from modules.media import theme


def make_qr(
    data: str,
    *,
    size: int = 200,
    fill: tuple[int, int, int] = (18, 30, 58),
    back: tuple[int, int, int] = theme.WHITE,
    border: int = 2,
) -> Image.Image:
    """
    QR kodni rasm sifatida qaytaradi.

    `ERROR_CORRECT_M` — 15% shikastlanishga chidamli. Telefon ekranidan
    yoki bosma qog'ozdan skanerlashda yetarli.
    """
    qr = qrcode.QRCode(
        version=None,               # avtomatik: ma'lumot hajmiga qarab
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    image = qr.make_image(fill_color=fill, back_color=back).convert("RGB")
    return image.resize((size, size), Image.Resampling.NEAREST)


def make_qr_rounded(
    data: str,
    *,
    size: int = 200,
    padding: int = 12,
    fill: tuple[int, int, int] = (18, 30, 58),
    back: tuple[int, int, int] = theme.WHITE,
) -> Image.Image:
    """
    Oq fonli, yumaloq burchakli QR — to'q fonda chiroyli ko'rinadi.
    """
    from PIL import ImageDraw

    inner = size - padding * 2
    qr_image = make_qr(data, size=inner, fill=fill, back=back, border=1)

    canvas = Image.new("RGB", (size, size), back)
    canvas.paste(qr_image, (padding, padding))

    #  Yumaloq burchak uchun niqob
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=16, fill=255)

    result = Image.new("RGB", (size, size), back)
    result.paste(canvas, (0, 0), mask)
    return result
