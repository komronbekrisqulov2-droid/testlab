"""
Test varaqalariga dinamik suv belgisi (watermark) tushirish.

O'quvchi testni ochganda, rasm ustiga uning ismi va Telegram ID-si
yarim-shaffof qilib tushiriladi:
    👤 Sardorbek Ergashev  ·  ID: 12345678  ·  TestLab

Agar o'quvchi 2-telefon bilan rasmga olib guruhga yoki do'stlariga
tashlasa, rasmning orqa fonidagi belgilar kim sizdirganini fosh qiladi.
"""

from __future__ import annotations

import io
from math import hypot

from PIL import Image, ImageDraw

from core.logging import get_logger
from modules.media.fonts import font

log = get_logger(__name__)


def apply_student_watermark(
    image_bytes: bytes,
    student_name: str,
    telegram_id: int,
) -> bytes:
    """
    Rasm ustiga o'quvchining shaxsiy suv belgisini tushiradi.

    Args:
        image_bytes: Asl rasmning baytlari (JPEG / PNG).
        student_name: O'quvchining to'liq ismi-familiyasi.
        telegram_id: Telegram identifikatori.

    Returns:
        Suv belgisi tushirilgan rasm baytlari (JPEG).
    """
    if not image_bytes:
        return image_bytes

    try:
        base_img = Image.open(io.BytesIO(image_bytes))
        width, height = base_img.size

        # RGBA rejimiga keltirish
        if base_img.mode != "RGBA":
            rgba_img = base_img.convert("RGBA")
        else:
            rgba_img = base_img.copy()

        # Shaffof qatlam
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        # Shrift o'lchamini rasm hajmiga qarab tanlash
        diag = hypot(width, height)
        font_size = max(14, min(36, int(diag * 0.016)))
        fnt = font(font_size, bold=True)

        stamp_text = f"{student_name} · ID: {telegram_id} · TestLab"

        # Bitta shtamp o'lchamini hisoblash
        dummy_draw = ImageDraw.Draw(overlay)
        bbox = dummy_draw.textbbox((0, 0), stamp_text, font=fnt)
        text_w = bbox[2] - bbox[0] + 40
        text_h = bbox[3] - bbox[1] + 20

        # Shtamp rasmini yaratish (kichik o'lchamda)
        stamp_img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
        stamp_draw = ImageDraw.Draw(stamp_img)

        # Matn rangi: yarim-shaffof oq/kulrang, nozik soya bilan
        stamp_draw.text((11, 6), stamp_text, font=fnt, fill=(0, 0, 0, 30))
        stamp_draw.text((10, 5), stamp_text, font=fnt, fill=(80, 100, 140, 48))

        # 25 daraja burchak ostida aylantirish
        rotated_stamp = stamp_img.rotate(25, expand=True, resample=Image.Resampling.BICUBIC)
        rw, rh = rotated_stamp.size

        # Butun rasm bo'ylab panjara tarzida takrorlash
        step_x = max(rw + 60, int(width * 0.32))
        step_y = max(rh + 60, int(height * 0.22))

        offset_x = 0
        for y in range(-rh // 2, height + rh, step_y):
            offset_x = (offset_x + step_x // 3) % step_x
            for x in range(-rw // 2 + offset_x, width + rw, step_x):
                overlay.alpha_composite(rotated_stamp, (x, y))

        # Pastki xavfsizlik lentasi (Footer badge)
        footer_h = max(26, int(height * 0.035))
        footer_font = font(max(11, int(footer_h * 0.55)), bold=True)
        footer_y = height - footer_h

        # Qoramtir shaffof tasma
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(
            [(0, footer_y), (width, height)],
            fill=(15, 23, 42, 180),
        )
        footer_text = f"🛡 TestLab Himoyasi · {student_name} (ID: {telegram_id}) · Nusxa olish taqiqlanadi"
        f_bbox = overlay_draw.textbbox((0, 0), footer_text, font=footer_font)
        f_w = f_bbox[2] - f_bbox[0]
        overlay_draw.text(
            ((width - f_w) // 2, footer_y + (footer_h - (f_bbox[3] - f_bbox[1])) // 2),
            footer_text,
            font=footer_font,
            fill=(241, 245, 249, 230),
        )

        # Asl rasmga ustiga yopishtirish
        result = Image.alpha_composite(rgba_img, overlay).convert("RGB")

        out = io.BytesIO()
        result.save(out, format="JPEG", quality=88, optimize=True)
        return out.getvalue()

    except Exception as error:
        log.warning("Suv belgisi tushirishda xatolik: %s, asl rasm yuboriladi", error)
        return image_bytes
