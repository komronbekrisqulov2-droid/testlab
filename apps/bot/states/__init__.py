"""
FSM holatlari.

Holat — bot foydalanuvchidan nima kutayotganini bildiradi. Masalan
`Registration.first_name` holatida yuborilgan matn ism deb qabul
qilinadi, test kodi deb emas.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """Ro'yxatdan o'tish: to'liq ism va familiya."""

    full_name = State()


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


class QuestionAppealState(StatesGroup):
    """O'quvchining savol bo'yicha e'tirozi / murojaati."""

    waiting_for_text = State()


class TeacherAppealReplyState(StatesGroup):
    """O'qituvchining o'quvchi e'tiroziga javobi."""

    waiting_for_reply = State()


class FeedbackState(StatesGroup):
    """Foydalanuvchining taklif yoki muammo murojaati."""

    waiting_for_message = State()


class AdminFeedbackReplyState(StatesGroup):
    """Adminning taklif/muammoga javobi."""

    waiting_for_reply = State()


class ClassroomCreate(StatesGroup):
    """Sinf / guruh yaratish."""

    name = State()


class RandomQuestionsCount(StatesGroup):
    """Randomizatsiyada har bir o'quvchiga nechta savol tushishi."""

    count = State()


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
    "QuestionAppealState",
    "TeacherAppealReplyState",
    "FeedbackState",
    "AdminFeedbackReplyState",
    "ClassroomCreate",
    "RandomQuestionsCount",
)




