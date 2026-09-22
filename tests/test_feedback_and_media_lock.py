"""
Taklif va muammo (Feedback) tizimi hamda albom yuklash lock'i sinovi.

Ishga tushirish:
    python tests/test_feedback_and_media_lock.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401

from apps.bot.keyboards.callbacks import FeedbackCB
from apps.bot.keyboards.inline import admin_feedback_reply_keyboard, main_menu
from apps.bot.texts import uz
from modules.identity.models import User


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}")
        raise AssertionError(f"Sinov muvaffaqiyatsiz: {name}")


async def main() -> None:
    print("\n--- 1. Callback va Klaviaturalar ---")
    cb = FeedbackCB(action="reply", target_id=12345678)
    packed = cb.pack()
    unpacked = FeedbackCB.unpack(packed)
    check("FeedbackCB pack/unpack", unpacked.action == "reply" and unpacked.target_id == 12345678)

    admin_kb = admin_feedback_reply_keyboard(12345678)
    check("admin_feedback_reply_keyboard tugmasi bor", len(admin_kb.inline_keyboard) == 1)
    btn = admin_kb.inline_keyboard[0][0]
    check("admin tugmasi matni to'g'ri", "javob" in btn.text.lower())

    dummy_user = User(
        telegram_id=999888,
        first_name="Testbek",
        last_name="Sinovchi",
        role="student",
        is_registered=True,
    )
    menu_kb = main_menu(dummy_user)
    has_feedback_btn = any(
        any("taklif" in (b.text or "").lower() for b in row)
        for row in menu_kb.inline_keyboard
    )
    check("Bosh menyuda 'Taklif va Muammo' tugmasi mavjud", has_feedback_btn)

    print("\n--- 2. Matnlar va Formatlash ---")
    notif_text = uz.feedback_admin_notification(dummy_user, text="Botda yangi dizayn kerak!")
    check("Adminga xabarda ism bor", "Testbek" in notif_text)
    check("Adminga xabarda ID bor", "999888" in notif_text)
    check("Adminga xabarda matn bor", "Botda yangi dizayn kerak!" in notif_text)

    reply_text = uz.feedback_user_reply("Taklifingiz ko'rib chiqildi, rahmat!")
    check("Foydalanuvchiga javob sarlavhasi bor", "ADMINISTRATOR" in reply_text)
    check("Foydalanuvchiga javob matni bor", "Taklifingiz ko'rib chiqildi" in reply_text)

    print("\n--- 3. Albom (Media-Group) Lock Mantiqi ---")
    from apps.bot.handlers.teacher.create import _user_locks

    lock = _user_locks[12345]
    check("Har bir foydalanuvchiga alohida Lock beriladi", isinstance(lock, asyncio.Lock))

    # Parallel 5 ta chaqiruv ketma-ketlikda kirishini tekshirish
    execution_order = []

    async def worker(idx: int):
        async with _user_locks[12345]:
            execution_order.append(f"start_{idx}")
            await asyncio.sleep(0.01)
            execution_order.append(f"end_{idx}")

    await asyncio.gather(*(worker(i) for i in range(3)))
    # Lock to'g'ri ishlagan bo'lsa, start_X va end_X bir-birini buzmasdan ketma-ket chiqadi
    is_serialized = all(
        execution_order[i].startswith("start_") and execution_order[i + 1].startswith("end_")
        for i in range(0, len(execution_order), 2)
    )
    check("Lock barcha parallel vazifalarni tartibli (serialized) bajardi", is_serialized)

    print("\n  BARCHA TESTLAR MUVAFFAQIYATLI O'TDI ✅\n")


if __name__ == "__main__":
    asyncio.run(main())
