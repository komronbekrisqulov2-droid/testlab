"""
Handler'lar.

RO'YXATDAN O'TKAZISH TARTIBI JUDA MUHIM
---------------------------------------

    1. errors     — global xato ushlagich
    2. start      — /start, ro'yxatdan o'tish, bosh menyu
    3. broadcast  — ommaviy xabar (admin panelidan OLDIN)
    4. admin      — o'z filtri bilan himoyalangan
    5. teacher    — test yaratish va boshqarish
    6. student    — javob berish, natijalar, reyting
    7. access     — huquqi yetmaganlarga chiroyli tushuntirish
    8. fallback   — qolgan hamma narsa (ENG OXIRIDA)

`access` ATAYLAB `teacher` dan KEYIN turadi: o'qituvchi bo'lganlar
yuqorida ushlanadi va bu yergacha yetib kelmaydi. Yetib kelgani —
demak huquqi yo'q, unga "Tushunmadim" emas, aniq tushuntirish kerak.

Agar `fallback` yuqoriroqda tursa — u barcha xabarlarni ushlab qolib,
qolgan handler'lar hech qachon ishlamaydi.

`teacher` `student` dan OLDIN turadi: o'qituvchi `Nom+abcdabcd` deb
yozganda bu test yaratish deb tushunilishi kerak, boshqa narsa deb emas.
"""

from __future__ import annotations

from aiogram import Dispatcher

from apps.bot.handlers.admin import broadcast as admin_broadcast
from apps.bot.handlers.admin import panel as admin_panel
from apps.bot.handlers.shared import access, errors, feedback, start
from apps.bot.handlers.student import answer as student_answer
from apps.bot.handlers.student import explanations as student_explanations
from apps.bot.handlers.student import mistakes as student_mistakes
from apps.bot.handlers.student import parent as student_parent
from apps.bot.handlers.student import result as student_result
from apps.bot.handlers.teacher import classroom as teacher_classroom
from apps.bot.handlers.teacher import create as teacher_create
from apps.bot.handlers.teacher import manage as teacher_manage
from core.logging import get_logger

log = get_logger(__name__)


def setup_routers(dispatcher: Dispatcher) -> None:
    """Router'larni to'g'ri tartibda ulaydi."""
    routers = (
        errors.router,
        start.router,
        feedback.router,
        #  Broadcast paneldan OLDIN: u `Broadcast.message` holatida
        #  ISTALGAN xabarni ushlashi kerak, panelning qidiruv handleri
        #  esa faqat matnni kutadi va rasmli xabarni yutib yuborardi.
        admin_broadcast.router,
        admin_panel.router,
        teacher_create.router,
        teacher_manage.router,
        teacher_classroom.router,
        student_explanations.router,
        student_mistakes.router,
        student_parent.router,
        student_answer.router,
        student_result.router,
        access.router,
        errors.fallback_router,
    )

    for router in routers:
        dispatcher.include_router(router)

    log.info("🔗 %d ta router ulandi", len(routers))


__all__ = ("setup_routers",)
