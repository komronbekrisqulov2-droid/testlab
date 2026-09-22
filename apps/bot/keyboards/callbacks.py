"""
Callback ma'lumot fabrikalari.

Telegram `callback_data` uchun **64 BAYT** chegarasi bor. Shuning uchun:
    * prefikslar qisqa ("m", "t", "a")
    * matn emas, faqat raqamlar uzatiladi
    * to'g'ri javob haqidagi ma'lumot HECH QACHON bu yerga qo'yilmaydi
      (foydalanuvchi callback_data ni ko'ra oladi)

aiogram `CallbackData` qiymatlarni avtomatik tekshiradi — buzuq yoki
soxta callback handler'ga umuman yetib bormaydi.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    """Bosh menyu va navigatsiya."""

    action: str
    #  main, help, profile, results, board, close, register, create, mytests


class TestCB(CallbackData, prefix="t"):
    """Test bilan ishlash."""

    action: str
    #  open, answer, images, manage, publish, archive, delete, delete_yes,
    #  timer_menu, set_timer, share_channel, post_results
    test_id: int = 0
    page: int = 1
    value: int = 0



class BuildCB(CallbackData, prefix="b"):
    """Test yaratish jarayoni."""

    action: str      # undo_photo, cancel
    test_id: int = 0


class CertCB(CallbackData, prefix="c"):
    """Sertifikat."""

    action: str      # issue, list, open
    attempt_id: int = 0
    cert_id: int = 0
    page: int = 1


class PeopleCB(CallbackData, prefix="p"):
    """Javob berganlar ro'yxati va Excel."""

    action: str      # list, excel, analysis
    test_id: int = 0
    page: int = 1


class AdminCB(CallbackData, prefix="a"):
    """Admin panel."""

    action: str
    #  panel, users, solvers, board, tests, search,
    #  user, ban, unban, role, excel_users, excel_solvers
    target_id: int = 0
    page: int = 1
    period: int = 0   # 0 = butun davr, 1/7/30 = kun


class PageCB(CallbackData, prefix="pg"):
    """Umumiy sahifalash."""

    scope: str       # mytests, results
    page: int = 1


class NoopCB(CallbackData, prefix="x"):
    """Bosilmaydigan tugma (sahifa ko'rsatkichi kabi)."""

    tag: str = "x"


class MistakeCB(CallbackData, prefix="mk"):
    """Xatolar ustida ishlash (retake)."""

    action: str      # hub, retake, answer, clear
    test_id: int = 0
    q_num: int = 0
    choice: str | None = None


class ParentCB(CallbackData, prefix="pr"):
    """Ota-ona ulanishi."""

    action: str      # hub, unlink
    target_id: int = 0


class ExplainCB(CallbackData, prefix="ex"):
    """Savollar yechimlari."""

    action: str      # list, view, edit
    test_id: int = 0
    q_num: int = 0


class AttemptCB(CallbackData, prefix="att"):
    """Urinish tahlili va ko'rish."""

    action: str      # view, list, card
    attempt_id: int = 0
    page: int = 1


class AppealCB(CallbackData, prefix="ap"):
    """Savol bo'yicha e'tiroz va murojaatlar."""

    action: str      # ask, reply, view, list
    test_id: int = 0
    q_num: int = 0
    appeal_id: int = 0
    target_user_id: int = 0

