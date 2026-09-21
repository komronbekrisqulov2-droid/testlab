"""
FSM holatlari.

Holat — bot foydalanuvchidan nima kutayotganini bildiradi. Masalan
`Registration.first_name` holatida yuborilgan matn ism deb qabul
qilinadi, test kodi deb emas.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """Ro'yxatdan o'tish: ism -> familiya -> telefon."""

    first_name = State()
    last_name = State()
    phone = State()


class Building(StatesGroup):
    """
    Rasmli test yaratish.

    BITTA holat — ikkita amal:
        rasm kelsa  -> testga qo'shiladi
        matn kelsa  -> javoblar kaliti deb o'qiladi va test e'lon qilinadi

    Nega bitta holat? "Rasmlar tugadi" degan alohida tugma keraksiz:
    kalitning kelishi o'zi rasmlar bosqichi tugaganini bildiradi.
    """

    active = State()


class Answering(StatesGroup):
    """Javob berish — qaysi test ochiqligi FSM ma'lumotida saqlanadi."""

    waiting = State()


class AdminSearch(StatesGroup):
    """Admin foydalanuvchi qidirmoqda."""

    query = State()


class Broadcast(StatesGroup):
    """
    Ommaviy xabar: matn -> ko'rib chiqish -> tasdiq.

    Tasdiq bosqichi ATAYLAB alohida. Ommaviy xabarni orqaga qaytarib
    bo'lmaydi — minglab odamga yuborilgach «bekor qilish» degan narsa
    yo'q. Shuning uchun yuborishdan oldin admin xabarni aynan qanday
    ko'rinishda borishini ko'radi va qabul qiluvchilar sonini biladi.
    """

    message = State()
    confirm = State()


class TestEdit(StatesGroup):
    """Testni tahrirlash: nom, kalit yoki media yangilash."""

    title = State()
    key = State()
    media = State()


class ChannelShare(StatesGroup):
    """Testni kanal/guruhga ulashish."""

    target = State()


class TestSchedule(StatesGroup):
    """Test jadvalini sozlash (ochilish va yopilish)."""

    start_time = State()
    end_time = State()


class ExplanationEdit(StatesGroup):
    """Savolga yechim / izoh kiritish (matn yoki fayl/video)."""

    waiting_text = State()
    waiting_content = State()


__all__ = (
    "Registration",
    "Building",
    "Answering",
    "AdminSearch",
    "Broadcast",
    "TestEdit",
    "TestSchedule",
    "ChannelShare",
    "ExplanationEdit",
)



