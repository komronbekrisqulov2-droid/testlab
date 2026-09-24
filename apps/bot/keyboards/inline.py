"""Inline klaviaturalar."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from apps.bot.keyboards.callbacks import (
    AdminCB,
    AttemptCB,
    BuildCB,
    CertCB,
    ClassCB,
    ExplainCB,
    FeedbackCB,
    MenuCB,
    MistakeCB,
    NoopCB,
    PageCB,
    ParentCB,
    PeopleCB,
    TestCB,
)
from apps.bot.texts import uz
from core.config import settings
from infrastructure.database.repository import Page
from modules.catalog.models import Test
from modules.identity.models import User



# ======================================================================
#  UMUMIY BLOKLAR
# ======================================================================

def home_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=uz.BTN_HOME, callback_data=MenuCB(action="main").pack()
    )


def back_button(callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=uz.BTN_BACK, callback_data=callback_data)


def home_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(home_button())
    return builder.as_markup()


def pagination_row(
    page: Page,
    make_callback,
) -> list[InlineKeyboardButton]:
    """
    Sahifalash qatori: ◀️ 2/7 ▶️

    `make_callback(page_number)` — kerakli callback_data ni qaytaruvchi
    funksiya. Har bir ro'yxat o'z callback turini ishlatadi.
    """
    if page.pages <= 1:
        return []

    row: list[InlineKeyboardButton] = []

    if page.has_prev:
        row.append(InlineKeyboardButton(text="◀️", callback_data=make_callback(page.page - 1)))

    row.append(
        InlineKeyboardButton(
            text=f"{page.page}/{page.pages}", callback_data=NoopCB().pack()
        )
    )

    if page.has_next:
        row.append(InlineKeyboardButton(text="▶️", callback_data=make_callback(page.page + 1)))

    return row


# ======================================================================
#  BOSH MENYU
# ======================================================================

def main_menu(user: User) -> InlineKeyboardMarkup:
    """
    Bosh menyu — roldan kelib chiqib tuziladi.

    O'quvchiga test yaratish tugmasi ko'rsatilmaydi: bosgan bilan
    "ruxsat yo'q" degan xabar chiqadi, bu esa noqulaylik.
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_ANSWER, callback_data=MenuCB(action="answer").pack()
        )
    )

    if user.is_teacher:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_CREATE, callback_data=MenuCB(action="create").pack()
            ),
            InlineKeyboardButton(
                text=uz.BTN_HOW_TO_CREATE, callback_data=MenuCB(action="how_to_create").pack()
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_MY_TESTS, callback_data=MenuCB(action="mytests").pack()
            ),
            InlineKeyboardButton(
                text="👥 Guruhlarim (Sinflar)", callback_data=ClassCB(action="list").pack()
            ),
        )

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_RESULTS, callback_data=MenuCB(action="results").pack()
        ),
        InlineKeyboardButton(
            text=uz.BTN_MISTAKES, callback_data=MistakeCB(action="hub").pack()
        ),
    )
    if not user.is_teacher:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_LEADERBOARD, callback_data=MenuCB(action="board").pack()
            ),
            InlineKeyboardButton(
                text="👥 Guruhlarim", callback_data=ClassCB(action="student_list").pack()
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_LEADERBOARD, callback_data=MenuCB(action="board").pack()
            ),
        )


    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_PROFILE, callback_data=MenuCB(action="profile").pack()
        ),
        InlineKeyboardButton(
            text=uz.BTN_HELP, callback_data=MenuCB(action="help").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_FEEDBACK, callback_data=FeedbackCB(action="open").pack()
        )
    )

    if user.is_admin:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_ADMIN, callback_data=AdminCB(action="panel").pack()
            )
        )

    return builder.as_markup()


def teacher_request_keyboard() -> InlineKeyboardMarkup:
    """«O'qituvchi bo'ling» ekrani."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_HOW_TO_CREATE,
            callback_data=MenuCB(action="how_to_create").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_REQUEST_TEACHER,
            callback_data=MenuCB(action="request_teacher").pack(),
        )
    )
    builder.row(home_button())
    return builder.as_markup()


def grant_teacher_keyboard(target_id: int) -> InlineKeyboardMarkup:
    """
    Adminga keladigan so'rov ostidagi tugma.

    Bitta bosishda ruxsat beriladi — admin panelga kirib qidirish
    shart emas.
    """
    from apps.bot.keyboards.callbacks import AdminCB

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_GRANT_TEACHER,
            #  `period=1` = o'qituvchi roli (admin/panel.py ga qarang)
            callback_data=AdminCB(
                action="role", target_id=target_id, page=1, period=1
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👤 Profilini ko'rish",
            callback_data=AdminCB(action="user", target_id=target_id, page=1).pack(),
        )
    )
    return builder.as_markup()


def register_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_REGISTER, callback_data=MenuCB(action="register").pack()
        )
    )
    return builder.as_markup()


# ======================================================================
#  TEST YARATISH
# ======================================================================

def building_keyboard(test_id: int, *, has_photo: bool) -> InlineKeyboardMarkup:
    """
    Yaratish jarayonidagi yagona klaviatura.

    «Rasmlar tayyor» tugmasi ATAYLAB yo'q — kalitni yozish o'zi rasmlar
    bosqichini yakunlaydi. Ortiqcha tugma foydalanuvchini chalkashtiradi.
    """
    builder = InlineKeyboardBuilder()

    if has_photo:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_UNDO_PHOTO,
                callback_data=BuildCB(action="undo_photo", test_id=test_id).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_HOW_TO_CREATE,
            callback_data=MenuCB(action="how_to_create").pack(),
        ),
        InlineKeyboardButton(
            text=uz.BTN_CANCEL,
            callback_data=BuildCB(action="cancel", test_id=test_id).pack(),
        ),
    )
    return builder.as_markup()


def published_keyboard(test: Test) -> InlineKeyboardMarkup:
    """E'lon qilingandan keyin."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_SHARE_CHANNEL,
            callback_data=TestCB(action="share_channel", test_id=test.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔗 Do'stlarga ulashish",
            switch_inline_query=f"{test.title} — test kodi: {test.number}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_PARTICIPANTS,
            callback_data=PeopleCB(action="list", test_id=test.id, page=1).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_MY_TESTS, callback_data=MenuCB(action="mytests").pack()
        ),
        InlineKeyboardButton(
            text=uz.BTN_CREATE, callback_data=MenuCB(action="create").pack()
        ),
    )
    builder.row(home_button())
    return builder.as_markup()


# ======================================================================
#  TEST YECHISH
# ======================================================================

def webapp_solve_button(test_id: int) -> InlineKeyboardButton:
    """
    Mini App tugmasi.

    Telegram qoidasi: WebApp faqat HTTPS bilan ishlaydi.
    Agar HTTPS bo'lsa (server/tunnel) to'g'ridan-to'g'ri Telegram ichida WebApp ochiladi.
    Agar HTTP bo'lsa (lokal tunnel bo'lmaganda), Telegram xato bermasligi uchun
    callback orqali tushuntirish beriladi.
    """
    url = f"{settings.webapp.base_url}/test/{test_id}"
    if url.startswith("https://"):
        return InlineKeyboardButton(
            text=uz.BTN_WEBAPP_SOLVE,
            web_app=WebAppInfo(url=url),
        )
    return InlineKeyboardButton(
        text=uz.BTN_WEBAPP_SOLVE,
        callback_data=TestCB(action="webapp_info", test_id=test_id).pack(),
    )


def test_card_keyboard(test_id: int, *, has_images: bool) -> InlineKeyboardMarkup:
    """
    Test kartochkasining tugmalari.

    Oqim: test raqami -> rasmlar (agar bor bo'lsa) -> shu kartochka.
    Bu yerdan o'quvchi javob berishga o'tadi — yangi xabar kelmaydi,
    shu kartochka ko'rsatmaga aylanadi (`answering_keyboard` ga).
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_ANSWER,
            callback_data=TestCB(action="answer", test_id=test_id).pack(),
        )
    )

    if settings.webapp.enabled:
        builder.row(webapp_solve_button(test_id))

    if has_images:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_SHOW_IMAGES,
                callback_data=TestCB(action="images", test_id=test_id).pack(),
            )
        )

    builder.row(home_button())
    return builder.as_markup()


def answering_keyboard(test_id: int, *, has_images: bool) -> InlineKeyboardMarkup:
    """Javob kutilayotgan paytdagi klaviatura."""
    builder = InlineKeyboardBuilder()

    if settings.webapp.enabled:
        builder.row(webapp_solve_button(test_id))

    if has_images:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_SHOW_IMAGES,
                callback_data=TestCB(action="images", test_id=test_id).pack(),
            )
        )

    #  Orqaga — kartochkaga qaytadi, bosh menyuga emas.
    #  O'quvchi tasodifan bosib test ma'lumotini yo'qotmasligi kerak.
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_BACK,
            callback_data=TestCB(action="open", test_id=test_id).pack(),
        ),
        InlineKeyboardButton(
            text=uz.BTN_HOME, callback_data=MenuCB(action="main").pack()
        ),
    )
    return builder.as_markup()



def result_keyboard(
    test_id: int,
    *,
    attempt_id: int = 0,
    can_get_certificate: bool = False,
    hide_analysis: bool = False,
) -> InlineKeyboardMarkup:
    """Natijadan keyingi tugmalar."""
    from apps.bot.keyboards.callbacks import AttemptCB, CertCB

    builder = InlineKeyboardBuilder()

    #  1. Rasmli natija kartochkasi (talab bo'yicha chiziladi)
    if attempt_id:
        builder.row(
            InlineKeyboardButton(
                text="🖼 Rasmli natija kartochkasi",
                callback_data=AttemptCB(action="card", attempt_id=attempt_id).pack(),
            )
        )

    #  2. Sertifikat — eng qimmatli amal
    if can_get_certificate and attempt_id:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_CERTIFICATE,
                callback_data=CertCB(action="issue", attempt_id=attempt_id).pack(),
            )
        )

    #  3. Savollar tahlili (agar test ochiq bo'lsa va kalitlar yashirilgan bo'lsa ko'rsatilmaydi)
    if attempt_id and not hide_analysis:
        builder.row(
            InlineKeyboardButton(
                text="🔍 Savollar tahlili",
                callback_data=AttemptCB(action="view", attempt_id=attempt_id).pack(),
            )
        )

    if not hide_analysis:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_EXPLANATIONS,
                callback_data=ExplainCB(action="list", test_id=test_id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_LEADERBOARD,
            callback_data=PeopleCB(action="list", test_id=test_id, page=1).pack(),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_RESULTS, callback_data=MenuCB(action="results").pack()
        )
    )
    builder.row(home_button())
    return builder.as_markup()


# ======================================================================
#  MENING TESTLARIM
# ======================================================================

def my_tests_keyboard(page: Page) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    #  Har bir test — alohida tugma (raqam va nom bilan)
    for test in page.items:
        title = test.title[:28] + ("…" if len(test.title) > 28 else "")
        builder.row(
            InlineKeyboardButton(
                text=f"№{test.number} · {title}",
                callback_data=TestCB(action="manage", test_id=test.id).pack(),
            )
        )

    row = pagination_row(page, lambda number: PageCB(scope="mytests", page=number).pack())
    if row:
        builder.row(*row)

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_CREATE, callback_data=MenuCB(action="create").pack()
        )
    )
    builder.row(home_button())
    return builder.as_markup()


def test_manage_keyboard(test: Test) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if test.time_limit_sec > 0:
        timer_text = f"⏱ Taymer: {test.time_limit_sec // 60} daqiqa"
    else:
        timer_text = "⏱ Taymer o'rnatish (Cheksiz)"

    builder.row(
        InlineKeyboardButton(
            text=timer_text,
            callback_data=TestCB(action="timer_menu", test_id=test.id).pack(),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="✏️ Testni tahrirlash",
            callback_data=TestCB(action="edit_menu", test_id=test.id).pack(),
        )
    )

    rand_text = f"🎲 Random: Yoqilgan ({test.random_questions_count or 'Hammasi'} ta) 🟢" if test.is_randomized else "🎲 Randomizatsiya: O'chirilgan ⚪"
    builder.row(
        InlineKeyboardButton(
            text=rand_text,
            callback_data=TestCB(action="random_menu", test_id=test.id).pack(),
        )
    )

    cls_name = test.classroom.name if (test.classroom_id and test.classroom) else None
    grp_text = f"👥 Guruh: {cls_name[:16]} 🔒" if cls_name else "👥 Guruhga biriktirish (Ochiq)"
    builder.row(
        InlineKeyboardButton(
            text=grp_text,
            callback_data=TestCB(action="group_menu", test_id=test.id).pack(),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_PARTICIPANTS,
            callback_data=PeopleCB(action="list", test_id=test.id, page=1).pack(),
        ),
        InlineKeyboardButton(
            text=uz.BTN_EXCEL,
            callback_data=PeopleCB(action="excel", test_id=test.id).pack(),
        ),
    )
    if settings.webapp.enabled and settings.webapp.url and settings.webapp.url.startswith("https://"):
        builder.row(
            InlineKeyboardButton(
                text="📈 Savollar tahlili (Gemini AI)",
                web_app=WebAppInfo(url=f"{settings.webapp.url}/analysis/{test.id}"),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="📈 Savollar tahlili (Gemini AI)",
                callback_data=PeopleCB(action="analysis", test_id=test.id, page=1).pack(),
            )
        )

    if test.media_count:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_SHOW_IMAGES,
                callback_data=TestCB(action="images", test_id=test.id).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="💡 Yechimlar / Izohlar",
            callback_data=ExplainCB(action="edit", test_id=test.id).pack(),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_SHARE_CHANNEL,
            callback_data=TestCB(action="share_channel", test_id=test.id).pack(),
        )
    )


    if test.channel_id:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_POST_RESULTS,
                callback_data=TestCB(action="post_results", test_id=test.id).pack(),
            )
        )

    if test.is_published:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_ARCHIVE,
                callback_data=TestCB(action="archive", test_id=test.id).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_PUBLISH,
                callback_data=TestCB(action="publish", test_id=test.id).pack(),
            )
        )


    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_DELETE,
            callback_data=TestCB(action="delete", test_id=test.id).pack(),
        )
    )
    builder.row(
        back_button(MenuCB(action="mytests").pack()),
        home_button(),
    )
    return builder.as_markup()


def test_edit_keyboard(test_id: int) -> InlineKeyboardMarkup:
    """Testni tahrirlash menyusi."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="✏️ Nomini o'zgartirish",
            callback_data=TestCB(action="edit_title", test_id=test_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔑 Javoblar kalitini tuzatish",
            callback_data=TestCB(action="edit_key", test_id=test_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🖼 Fayl / Rasm qo'shish",
            callback_data=TestCB(action="edit_media", test_id=test_id).pack(),
        )
    )
    builder.row(
        back_button(TestCB(action="manage", test_id=test_id).pack()),
        home_button(),
    )
    return builder.as_markup()



def timer_select_keyboard(test: Test) -> InlineKeyboardMarkup:
    """Taymer, tezkor ochish/yopish va jadval sozlamalari ekrani."""
    builder = InlineKeyboardBuilder()

    # 1. Tezkor ochish / yopish holati
    if test.is_published:
        builder.row(
            InlineKeyboardButton(
                text="🔴 Testni hozir yopish (Qulflash)",
                callback_data=TestCB(action="toggle_status", test_id=test.id).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🟢 Testni hozir ochish (Faollashtirish)",
                callback_data=TestCB(action="toggle_status", test_id=test.id).pack(),
            )
        )

    # 2. Avtomatik jadval (Starts at / Ends at)
    from core.datetime_utils import fmt_datetime
    start_label = f"🟢 Ochilish: {fmt_datetime(test.starts_at)}" if test.starts_at else "➕ Ochilish vaqtini kiritish"
    end_label = f"🔴 Yopilish: {fmt_datetime(test.ends_at)}" if test.ends_at else "➕ Yopilish vaqtini kiritish"

    builder.row(
        InlineKeyboardButton(
            text=start_label,
            callback_data=TestCB(action="sched_start", test_id=test.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=end_label,
            callback_data=TestCB(action="sched_end", test_id=test.id).pack(),
        )
    )
    if test.starts_at or test.ends_at:
        builder.row(
            InlineKeyboardButton(
                text="❌ Jadval vaqtlarini o'chirish",
                callback_data=TestCB(action="clear_sched", test_id=test.id).pack(),
            )
        )

    # 3. Urinish taymeri presetlari
    presets = [
        (15, "⏱ 15 daqiqa"),
        (30, "⏱ 30 daqiqa"),
        (45, "⏱ 45 daqiqa"),
        (60, "⏱ 60 daqiqa (1 soat)"),
        (90, "⏱ 90 daqiqa (1.5 soat)"),
        (120, "⏱ 120 daqiqa (2 soat)"),
        (0, "♾ Cheksiz (Vaqtsiz)"),
    ]

    for mins, label in presets:
        is_active = (test.time_limit_sec == mins * 60) or (mins == 0 and test.time_limit_sec == 0)
        mark = " ✅" if is_active else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{label}{mark}",
                callback_data=TestCB(action="set_timer", test_id=test.id, value=mins).pack(),
            )
        )

    builder.row(
        back_button(TestCB(action="manage", test_id=test.id).pack()),
        home_button(),
    )
    return builder.as_markup()


def confirm_delete_keyboard(test_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🗑 Ha, o'chirilsin",
            callback_data=TestCB(action="delete_yes", test_id=test_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_BACK,
            callback_data=TestCB(action="manage", test_id=test_id).pack(),
        )
    )
    return builder.as_markup()


# ======================================================================
#  JAVOB BERGANLAR
# ======================================================================

def participants_keyboard(
    test_id: int,
    page: Page,
    *,
    back_callback: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if not page.is_empty:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_EXCEL,
                callback_data=PeopleCB(action="excel", test_id=test_id).pack(),
            )
        )

    row = pagination_row(
        page,
        lambda number: PeopleCB(action="list", test_id=test_id, page=number).pack(),
    )
    if row:
        builder.row(*row)

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_REFRESH,
            callback_data=PeopleCB(action="list", test_id=test_id, page=page.page).pack(),
        )
    )
    builder.row(back_button(back_callback), home_button())
    return builder.as_markup()


def subscription_keyboard(channels: list[str]) -> InlineKeyboardMarkup:
    """
    Majburiy obuna ekrani: kanal havolalari + tekshirish tugmasi.

    Havolasi yo'q kanal (yopiq kanal ID bilan berilgan) tugmasiz
    qoladi — matnda sanab o'tiladi. Ishlamaydigan tugma ko'rsatgandan
    ko'ra ko'rsatmagan yaxshiroq.
    """
    builder = InlineKeyboardBuilder()

    for channel in channels:
        link = uz.channel_link(channel)
        if link:
            builder.row(
                InlineKeyboardButton(
                    text=f"📢 {uz.channel_label(channel)}", url=link
                )
            )

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_CHECK_SUBSCRIPTION,
            callback_data=MenuCB(action="check_sub").pack(),
        )
    )
    return builder.as_markup()


def analysis_keyboard(
    test_id: int,
    page: Page,
    *,
    back_callback: str,
) -> InlineKeyboardMarkup:
    """
    Savollar tahlili ostidagi tugmalar.

    Sahifalash uchun `Page` obyekti ishlatiladi (elementlarsiz, faqat
    sanoq bilan) — shunda tahlil ham qolgan ro'yxatlar bilan bir xil
    ko'rinadi va `pagination_row` qayta yozilmaydi.
    """
    builder = InlineKeyboardBuilder()

    row = pagination_row(
        page,
        lambda number: PeopleCB(action="analysis", test_id=test_id, page=number).pack(),
    )
    if row:
        builder.row(*row)

    if settings.webapp.enabled and settings.webapp.url and settings.webapp.url.startswith("https://"):
        builder.row(
            InlineKeyboardButton(
                text="🤖 Gemini AI Tahlili (Mini App)",
                web_app=WebAppInfo(url=f"{settings.webapp.url}/analysis/{test_id}"),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_EXCEL,
            callback_data=PeopleCB(action="excel", test_id=test_id).pack(),
        )
    )
    builder.row(back_button(back_callback), home_button())
    return builder.as_markup()


# ======================================================================
#  RO'YXATLAR (natijalarim, reyting)
# ======================================================================

def results_keyboard(page: Page) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Har bir yechilgan test tahlilini ko'rish uchun tugmalar
    for att in page.items:
        test_title = att.test.title if att.test else f"Test #{att.test_id}"
        test_title = test_title[:22] + ("…" if len(test_title) > 22 else "")
        mark = "✅" if att.is_passed else "❌"
        builder.row(
            InlineKeyboardButton(
                text=f"{mark} {test_title} ({att.percentage:g}%)",
                callback_data=AttemptCB(action="view", attempt_id=att.id, page=page.page).pack(),
            )
        )

    row = pagination_row(page, lambda number: PageCB(scope="results", page=number).pack())
    if row:
        builder.row(*row)

    builder.row(
        InlineKeyboardButton(
            text="🎓 Sertifikatlar markazi",
            callback_data=CertCB(action="hub").pack(),
        )
    )
    builder.row(home_button())
    return builder.as_markup()


def attempt_detail_keyboard(
    test_id: int,
    attempt_id: int,
    *,
    has_mistakes: bool = False,
    can_certify: bool = False,
    page: int = 1,
) -> InlineKeyboardMarkup:
    """Bitta yechilgan test tahlili ekrani tugmalari."""
    from apps.bot.keyboards.callbacks import AppealCB, AttemptCB, CertCB, ExplainCB, MistakeCB

    builder = InlineKeyboardBuilder()

    # 1. O'qituvchi yuklagan savollar yechimlari / tushuntirishlari
    builder.row(
        InlineKeyboardButton(
            text="💡 Savollar yechimlari (Izohlar)",
            callback_data=ExplainCB(action="list", test_id=test_id).pack(),
        )
    )

    # 2. Agar xatolar bo'lsa — xatolar ustida ishlash
    if has_mistakes:
        builder.row(
            InlineKeyboardButton(
                text="🎯 Xatolar ustida ishlash (Qayta yechish)",
                callback_data=MistakeCB(action="hub").pack(),
            )
        )

    # 3. Sertifikat olish
    if can_certify:
        builder.row(
            InlineKeyboardButton(
                text="📜 Sertifikatni yuklab olish",
                callback_data=CertCB(action="issue", attempt_id=attempt_id).pack(),
            )
        )

    # 4. Rasmli natija kartochkasi
    builder.row(
        InlineKeyboardButton(
            text="🖼 Rasmli natija kartochkasi",
            callback_data=AttemptCB(action="card", attempt_id=attempt_id, page=page).pack(),
        )
    )

    builder.row(
        back_button(PageCB(scope="results", page=page).pack()),
        home_button(),
    )
    return builder.as_markup()


def personal_ranking_keyboard() -> InlineKeyboardMarkup:
    """Shaxsiy reyting ekrani klaviaturasi."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🎓 Sertifikat olish",
            callback_data=CertCB(action="hub").pack(),
        ),
        InlineKeyboardButton(
            text="📊 Natijalarim",
            callback_data=MenuCB(action="results").pack(),
        ),
    )
    builder.row(home_button())
    return builder.as_markup()


def notification_keyboard(test_id: int) -> InlineKeyboardMarkup:
    """
    O'qituvchiga keladigan «yangi javob» xabari ostidagi tugmalar.

    Bir bosishda to'liq ro'yxatga yoki Excel'ga o'tadi — panelni
    qidirib yurish shart emas.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_PARTICIPANTS,
            callback_data=PeopleCB(action="list", test_id=test_id, page=1).pack(),
        ),
        InlineKeyboardButton(
            text=uz.BTN_EXCEL,
            callback_data=PeopleCB(action="excel", test_id=test_id).pack(),
        ),
    )
    return builder.as_markup()


def simple_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(back_button(MenuCB(action="main").pack()))
    return builder.as_markup()


# ======================================================================
#  SMART UX: PROFIL, XATOLAR VA OTA-ONA
# ======================================================================

def profile_keyboard(is_teacher: bool = False) -> InlineKeyboardMarkup:
    """Profil ekrani klaviaturasi."""
    builder = InlineKeyboardBuilder()
    if not is_teacher:
        builder.row(
            InlineKeyboardButton(
                text="👥 Mening guruhlarim",
                callback_data=ClassCB(action="student_list").pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_LINK_PARENT,
            callback_data=ParentCB(action="hub").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_MISTAKES,
            callback_data=MistakeCB(action="hub").pack(),
        )
    )
    builder.row(home_button())
    return builder.as_markup()


def mistakes_hub_keyboard(has_mistakes: bool) -> InlineKeyboardMarkup:
    """Xatolar daftari boshqaruv klaviaturasi."""
    builder = InlineKeyboardBuilder()
    if has_mistakes:
        builder.row(
            InlineKeyboardButton(
                text="🚀 Xatolarni qayta yechish",
                callback_data=MistakeCB(action="retake").pack(),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🧹 Xatolarni tozalash",
                callback_data=MistakeCB(action="clear").pack(),
            )
        )
    builder.row(home_button())
    return builder.as_markup()


def mistake_question_keyboard(test_id: int, q_num: int) -> InlineKeyboardMarkup:
    """Xatolar ustida ishlashda bitta savol uchun javob tanlash klaviaturasi."""
    builder = InlineKeyboardBuilder()
    options = ["A", "B", "C", "D", "E"]
    buttons = [
        InlineKeyboardButton(
            text=opt,
            callback_data=MistakeCB(action="answer", test_id=test_id, q_num=q_num, choice=opt).pack(),
        )
        for opt in options
    ]
    builder.row(*buttons[:4])
    builder.row(
        buttons[4],
        InlineKeyboardButton(
            text="💡 Yechimni ko'rish",
            callback_data=ExplainCB(action="view", test_id=test_id, q_num=q_num).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⏭ O'tkazib yuborish",
            callback_data=MistakeCB(action="retake").pack(),
        ),
        home_button(),
    )
    return builder.as_markup()


def parent_hub_keyboard(parents: list) -> InlineKeyboardMarkup:
    """Ota-ona / repetitor boshqaruv ekrani."""
    builder = InlineKeyboardBuilder()
    for p in parents:
        name = p.parent_name or f"ID {p.parent_telegram_id}"
        builder.row(
            InlineKeyboardButton(
                text=f"❌ {name} ni uzish",
                callback_data=ParentCB(action="unlink", target_id=p.parent_telegram_id).pack(),
            )
        )
    builder.row(
        back_button(MenuCB(action="profile").pack()),
        home_button(),
    )
    return builder.as_markup()


def explanations_list_keyboard(test_id: int, questions_count: int, explanations: dict) -> InlineKeyboardMarkup:
    """Test savollarining yechimlarini ko'rish ro'yxati."""
    builder = InlineKeyboardBuilder()

    # Agar butun test uchun umumiy yechim fayli yoki video yuklangan bo'lsa
    if 0 in explanations:
        gen = explanations[0]
        if gen.media_type == "document":
            btn_title = "📁 To'liq yechim fayli (PDF/DOCX)"
        elif gen.media_type == "video":
            btn_title = "🎬 Yechim videosini ko'rish"
        else:
            btn_title = "🖼 To'liq yechim rasmi"

        builder.row(
            InlineKeyboardButton(
                text=btn_title,
                callback_data=ExplainCB(action="view", test_id=test_id, q_num=0).pack(),
            )
        )

    row = []
    for q in range(1, questions_count + 1):
        icon = "💡" if q in explanations else "❓"
        row.append(
            InlineKeyboardButton(
                text=f"{icon} {q}",
                callback_data=ExplainCB(action="view", test_id=test_id, q_num=q).pack(),
            )
        )
        if len(row) == 5:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)

    builder.row(
        back_button(MenuCB(action="results").pack()),
        home_button(),
    )
    return builder.as_markup()


def single_explanation_keyboard(test_id: int, q_num: int) -> InlineKeyboardMarkup:
    """Bitta savol yechimi ko'rilganda chiqadigan klaviatura."""
    from apps.bot.keyboards.callbacks import ExplainCB

    builder = InlineKeyboardBuilder()

    # Orqaga barcha yechimlar ro'yxatiga qaytish
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Barcha savollar yechimlari",
            callback_data=ExplainCB(action="list", test_id=test_id).pack(),
        ),
        home_button(),
    )
    return builder.as_markup()


def appeal_teacher_reply_keyboard(
    appeal_id: int, student_id: int, test_id: int, q_num: int
) -> InlineKeyboardMarkup:
    """O'qituvchiga kelgan murojaat ostidagi boshqaruv tugmalari."""
    from apps.bot.keyboards.callbacks import AppealCB, TestCB

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✍️ O'quvchiga javob qaytarish",
            callback_data=AppealCB(
                action="reply",
                test_id=test_id,
                q_num=q_num,
                appeal_id=appeal_id,
                target_user_id=student_id,
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔧 Testni boshqarish (Kalitni tuzatish)",
            callback_data=TestCB(action="manage", test_id=test_id).pack(),
        )
    )
    return builder.as_markup()


def admin_feedback_reply_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    """Admin uchun taklif/muammoga javob berish tugmasi."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✍️ Foydalanuvchiga javob berish",
            callback_data=FeedbackCB(action="reply", target_id=target_user_id).pack(),
        )
    )
    return builder.as_markup()


def test_random_keyboard(test: Test) -> InlineKeyboardMarkup:
    """Randomizatsiya sozlamalari ekrani."""
    builder = InlineKeyboardBuilder()

    # 1. Yoqish / o'chirish
    if test.is_randomized:
        builder.row(
            InlineKeyboardButton(
                text="🔴 Randomizatsiyani o'chirish",
                callback_data=TestCB(action="toggle_random", test_id=test.id).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🟢 Randomizatsiyani yoqish",
                callback_data=TestCB(action="toggle_random", test_id=test.id).pack(),
            )
        )

    # 2. Savollar soni
    builder.row(
        InlineKeyboardButton(
            text="🔢 Savollar sonini belgilash",
            callback_data=TestCB(action="set_rand_count", test_id=test.id).pack(),
        )
    )
    if test.random_questions_count:
        builder.row(
            InlineKeyboardButton(
                text="♾ Barcha savollarni aralashtirish",
                callback_data=TestCB(action="set_rand_all", test_id=test.id).pack(),
            )
        )

    builder.row(
        back_button(TestCB(action="manage", test_id=test.id).pack()),
        home_button(),
    )
    return builder.as_markup()


def test_group_select_keyboard(test: Test, classrooms: list) -> InlineKeyboardMarkup:
    """Testni ma'lum sinf/guruhga biriktirish klaviaturasi."""
    builder = InlineKeyboardBuilder()

    for cls in classrooms:
        is_current = (test.classroom_id == cls.id)
        mark = " ✅" if is_current else ""
        builder.row(
            InlineKeyboardButton(
                text=f"👥 {cls.name[:25]}{mark}",
                callback_data=TestCB(action="set_group", test_id=test.id, value=cls.id).pack(),
            )
        )

    # Guruhsiz (barchaga ochiq)
    is_open = (test.classroom_id is None)
    open_mark = " ✅" if is_open else ""
    builder.row(
        InlineKeyboardButton(
            text=f"🌐 Barchaga ochiq (Guruhsiz){open_mark}",
            callback_data=TestCB(action="set_group", test_id=test.id, value=0).pack(),
        )
    )

    builder.row(
        back_button(TestCB(action="manage", test_id=test.id).pack()),
        home_button(),
    )
    return builder.as_markup()


def classrooms_list_keyboard(classrooms: list) -> InlineKeyboardMarkup:
    """O'qituvchi guruhlari ro'yxati."""
    builder = InlineKeyboardBuilder()

    for cls in classrooms:
        builder.row(
            InlineKeyboardButton(
                text=f"👥 {cls.name[:28]} ({cls.members_count} o'quvchi)",
                callback_data=ClassCB(action="view", class_id=cls.id).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="➕ Yangi guruh yaratish",
            callback_data=ClassCB(action="create").pack(),
        )
    )
    builder.row(home_button())
    return builder.as_markup()


def classroom_detail_keyboard(cls) -> InlineKeyboardMarkup:
    """Bitta guruh tafsilotlari ekrani."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📊 Sinf reytingi (Peshqadamlar)",
            callback_data=ClassCB(action="ranking", class_id=cls.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👥 O'quvchilar ro'yxati",
            callback_data=ClassCB(action="students", class_id=cls.id).pack(),
        ),
        InlineKeyboardButton(
            text="📝 Guruh testlari",
            callback_data=ClassCB(action="tests", class_id=cls.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Guruhni o'chirish",
            callback_data=ClassCB(action="del_conf", class_id=cls.id).pack(),
        )
    )
    builder.row(
        back_button(ClassCB(action="list").pack()),
        home_button(),
    )
    return builder.as_markup()


def classroom_ranking_keyboard(class_id: int, is_teacher: bool = True) -> InlineKeyboardMarkup:
    """Guruh reytingi menyusi."""
    builder = InlineKeyboardBuilder()
    back_target = ClassCB(action="view", class_id=class_id).pack() if is_teacher else ClassCB(action="student_view", class_id=class_id).pack()
    builder.row(
        back_button(back_target),
        home_button(),
    )
    return builder.as_markup()


def classroom_students_keyboard(class_id: int, members: list, page: int = 1) -> InlineKeyboardMarkup:
    """Guruh o'quvchilari ro'yxati."""
    builder = InlineKeyboardBuilder()

    for m in members:
        user_name = m.user.full_name[:22] if m.user else f"ID: {m.user_id}"
        builder.row(
            InlineKeyboardButton(
                text=f"👤 {user_name}",
                callback_data=NoopCB().pack(),
            ),
            InlineKeyboardButton(
                text="❌ Chiqarish",
                callback_data=ClassCB(action="remove_user", class_id=class_id, target_id=m.user_id).pack(),
            ),
        )

    builder.row(
        back_button(ClassCB(action="view", class_id=class_id).pack()),
        home_button(),
    )
    return builder.as_markup()


def student_classrooms_list_keyboard(classrooms: list) -> InlineKeyboardMarkup:
    """O'quvchi a'zo bo'lgan guruhlar ro'yxati."""
    builder = InlineKeyboardBuilder()

    for cls in classrooms:
        builder.row(
            InlineKeyboardButton(
                text=f"🏫 {cls.name[:28]}",
                callback_data=ClassCB(action="student_view", class_id=cls.id).pack(),
            )
        )

    builder.row(home_button())
    return builder.as_markup()


def student_classroom_detail_keyboard(class_id: int) -> InlineKeyboardMarkup:
    """O'quvchi uchun guruh tafsilotlari ekrani."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📊 Sinf reytingi (Peshqadamlar)",
            callback_data=ClassCB(action="ranking", class_id=class_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🚪 Guruhdan chiqish",
            callback_data=ClassCB(action="student_leave", class_id=class_id).pack(),
        )
    )
    builder.row(
        back_button(ClassCB(action="student_list").pack()),
        home_button(),
    )
    return builder.as_markup()


