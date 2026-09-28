"""
Testni ishlaganlar ro'yxati (participants list) sinovi.
"""

from __future__ import annotations

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401
from modules.registry import Base  # noqa: F401

from apps.bot.keyboards.inline import test_card_keyboard, result_keyboard, participants_keyboard
from apps.bot.keyboards.callbacks import PeopleCB
from apps.bot.texts import uz
from infrastructure.database.repository import Page
from modules.catalog.models import Test
from modules.assessment.models import Attempt
from modules.identity.models import User

def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}")
        raise AssertionError(label)

def test_participants_text_format():
    print("\n--- 1. Matn formati (rasmdagidek) ---")
    author = User(id=1, telegram_id=999888, first_name="Saxobiddin", last_name="Karimov")
    test = Test(
        id=1,
        number=1,
        title="Matematika",
        questions_count=30,
        author=author,
    )

    user1 = User(id=10, telegram_id=111, first_name="Suxrobjon", last_name="Ismoilov")
    user2 = User(id=11, telegram_id=222, first_name="Shamshodbek", last_name="Hamdamqulov")
    att1 = Attempt(id=101, user=user1, score=29, correct_count=29)
    att2 = Attempt(id=102, user=user2, score=29, correct_count=29)

    page = Page(items=[att1, att2], total=39, page=1, per_page=25)
    text = uz.participants_page(test, page, start=0)

    print("Hosil bo'lgan matn:\n" + text)

    check("1-test haqida ma'lumotlar mavjud", "1-test haqida ma'lumotlar" in text)
    check("📋Test nomi:  Matematika mavjud", "📋Test nomi:  Matematika" in text)
    check("📝Test kodi: 1 mavjud", "📝Test kodi: 1" in text)
    check("🔢Savollar soni: 30 ta mavjud", "🔢Savollar soni: 30 ta" in text)
    check("👤Test yaratuvchisi mavjud", "👤Test yaratuvchisi:" in text and "Saxobiddin Karimov" in text)
    check("Testda qatnashganlar soni: 39 mavjud", "Testda qatnashganlar soni: 39" in text)
    check("1. Suxrobjon Ismoilov 29 ball mavjud", "1. Suxrobjon Ismoilov 29 ball" in text)
    check("2. Shamshodbek Hamdamqulov 29 ball mavjud", "2. Shamshodbek Hamdamqulov 29 ball" in text)

def test_keyboards():
    print("\n--- 2. Klaviaturadagi tugmalar ---")
    card_kb = test_card_keyboard(1, has_images=False)
    found_card_btn = False
    for row in card_kb.inline_keyboard:
        for btn in row:
            if btn.text == "👥 Testni ishlaganlar":
                found_card_btn = True
                cb = PeopleCB.unpack(btn.callback_data)
                check("test_id to'g'ri", cb.test_id == 1)
                check("action to'g'ri", cb.action == "list")
    check("test_card_keyboard da '👥 Testni ishlaganlar' tugmasi bor", found_card_btn)

    res_kb = result_keyboard(1, attempt_id=100)
    found_res_btn = False
    for row in res_kb.inline_keyboard:
        for btn in row:
            if btn.text == "👥 Testni ishlaganlar":
                found_res_btn = True
    check("result_keyboard da '👥 Testni ishlaganlar' tugmasi bor", found_res_btn)

if __name__ == "__main__":
    test_participants_text_format()
    test_keyboards()
    print("\n🎉 Barcha testlar muvaffaqiyatli yakunlandi!")
