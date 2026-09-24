"""
Ro'yxatdan o'tish validatsiyasi va Anti-cheat (watermark, protect_content) testlari.
"""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.bot.handlers.shared.start import _validate_full_name
from apps.bot.texts import uz
from modules.media.watermark import apply_student_watermark


class TestRegistrationValidation(unittest.TestCase):
    """Ism va familiya validatsiyasini tekshirish."""

    def test_valid_standard_names(self):
        names, err = _validate_full_name("Ali Valiyev")
        self.assertIsNone(err)
        self.assertEqual(names, ("Ali", "Valiyev"))

        names, err = _validate_full_name("Aziza Karimova")
        self.assertIsNone(err)
        self.assertEqual(names, ("Aziza", "Karimova"))

    def test_valid_uzbek_apostrophes(self):
        # Oddiy apostrof
        names, err = _validate_full_name("O'tkir Hoshimov")
        self.assertIsNone(err)
        self.assertEqual(names, ("O'tkir", "Hoshimov"))

        # Lotin Oʻ (U+02BB)
        names, err = _validate_full_name("Oʻtkir Hoshimov")
        self.assertIsNone(err)
        self.assertEqual(names, ("O'tkir", "Hoshimov"))

        # Qiya apostrof G‘ (U+2018)
        names, err = _validate_full_name("G‘ayratbek Saidov")
        self.assertIsNone(err)
        self.assertEqual(names, ("G'ayratbek", "Saidov"))

        # O'g'li / Qizi bilan
        names, err = _validate_full_name("Akmal o'g'li Sardorbek")
        self.assertIsNone(err)
        self.assertIsNotNone(names)

    def test_multi_part_names(self):
        names, err = _validate_full_name("Karimova Aziza Akmal qizi")
        self.assertIsNone(err)
        self.assertIsNotNone(names)
        self.assertEqual(names[0], "Karimova")
        self.assertIn("Aziza", names[1])

    def test_invalid_names(self):
        # Bitta so'z
        names, err = _validate_full_name("Ali")
        self.assertIsNone(names)
        self.assertEqual(err, uz.NAME_TOO_SHORT)

        names, err = _validate_full_name("Jasurbek")
        self.assertIsNone(names)
        self.assertEqual(err, uz.ONE_WORD_NAME)

        # Raqam aralashgan
        names, err = _validate_full_name("Ali123 Valiyev")
        self.assertIsNone(names)
        self.assertEqual(err, uz.FULL_NAME_INVALID)

        # Maxsus belgilar
        names, err = _validate_full_name("Ali @ Valiyev")
        self.assertIsNone(names)
        self.assertEqual(err, uz.FULL_NAME_INVALID)

        # Juda qisqa
        names, err = _validate_full_name("A B")
        self.assertIsNone(names)
        self.assertEqual(err, uz.NAME_TOO_SHORT)


class TestAntiCheatWatermark(unittest.TestCase):
    """Suv belgisi tushirish modulini tekshirish."""

    def setUp(self):
        # Test uchun oddiy oq rasm yaratamiz
        img = Image.new("RGB", (600, 800), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        self.sample_bytes = buf.getvalue()

    def test_apply_student_watermark(self):
        result_bytes = apply_student_watermark(
            self.sample_bytes,
            student_name="Sardorbek Ergashev",
            telegram_id=987654321,
        )

        self.assertIsNotNone(result_bytes)
        self.assertGreater(len(result_bytes), 0)

        # Natijaviy rasm to'g'ri JPEG ekanligini va o'lchami saqlanganini tekshirish
        res_img = Image.open(io.BytesIO(result_bytes))
        self.assertEqual(res_img.size, (600, 800))
        self.assertEqual(res_img.format, "JPEG")

    def test_empty_bytes_fallback(self):
        res = apply_student_watermark(b"", "Ali Valiyev", 12345)
        self.assertEqual(res, b"")


if __name__ == "__main__":
    unittest.main()
