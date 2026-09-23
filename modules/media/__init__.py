"""
Rasm generatsiyasi.

Bu modul Pillow bilan ishlaydi va bazaga ham, Telegram'ga ham bog'liq
emas — unga faqat tayyor ma'lumot (dataclass) beriladi, u PNG baytlarini
qaytaradi. Shu sababli uni botsiz sinash mumkin.

    fonts        shrift yuklash (zaxira zanjiri bilan)
    theme        ranglar, gradient, ramka, matn joylashuvi
    result_card  natija kartochkasi (ulashiladigan)
    poster       test reklamasi (guruhga tashlash uchun)
    certificate  sertifikat (QR kod bilan)
"""

from modules.media import certificate, fonts, poster, result_card, theme, watermark

__all__ = ("fonts", "theme", "result_card", "poster", "certificate", "watermark")
