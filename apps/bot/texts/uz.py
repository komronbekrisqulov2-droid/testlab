"""
O'zbekcha matnlar.

Bu yerda BARCHA foydalanuvchiga ko'rinadigan matnlar to'plangan.
Handler'larda matn yozilmaydi — faqat shu moduldan chaqiriladi.
Shunday qilib ertaga rus/ingliz tilini qo'shish faqat yangi fayl
yozishga aylanadi.

Formatlash: Telegram HTML (<b>, <i>, <code>, <a>).
Foydalanuvchi kiritgan har qanday matn `escape()` dan o'tkaziladi.
"""

from __future__ import annotations

from html import escape as _escape

from core.datetime_utils import fmt_datetime, fmt_duration
from modules.assessment.models import Attempt
from modules.catalog.answer_key import format_key
from modules.catalog.models import Test
from modules.identity.models import User

LINE = "━━━━━━━━━━━━━━━━━━━━"


def escape(value: str | None) -> str:
    """Foydalanuvchi matnini HTML uchun xavfsiz qiladi."""
    return _escape(str(value or ""), quote=False)


# ======================================================================
#  TUGMALAR
# ======================================================================

BTN_BACK = "⬅️ Orqaga"
BTN_HOME = "🏠 Bosh menyu"
BTN_CANCEL = "✖️ Bekor qilish"
BTN_CLOSE = "✖️ Yopish"
BTN_REFRESH = "🔄 Yangilash"
BTN_SKIP = "⏭ O'tkazib yuborish"

BTN_REGISTER = "🪪 Ro'yxatdan o'tish"
BTN_SHARE_PHONE = "📱 Raqamni yuborish"

BTN_ANSWER = "✅ Testga javob berish"
BTN_CREATE = "➕ Test yaratish"
BTN_HOW_TO_CREATE = "❓ Test qanday yaratiladi?"
BTN_MY_TESTS = "📚 Mening testlarim"
BTN_RESULTS = "📊 Natijalarim"
BTN_LEADERBOARD = "🏆 Reyting"
BTN_PROFILE = "👤 Profil"
BTN_HELP = "❓ Yordam"
BTN_ADMIN = "🛠 Admin panel"

BTN_UNDO_PHOTO = "⬅️ Oxirgi rasmni o'chirish"
BTN_SHOW_IMAGES = "🖼 Test rasmlarini ko'rish"
BTN_PARTICIPANTS = "👥 Javob berganlar"
BTN_TEST_PARTICIPANTS = "👥 Testni ishlaganlar"
BTN_TEST_SOLVERS = "👥 Testni ishlaganlar"
BTN_EXCEL = "📊 Excel jadval"
BTN_ANALYSIS = "📈 Savollar tahlili"
BTN_PUBLISH = "🚀 E'lon qilish"
BTN_DELETE = "🗑 O'chirish"
BTN_ARCHIVE = "📦 Arxivlash"
BTN_SHARE_CHANNEL = "📢 Kanal/Guruhga ulashish"
BTN_POST_RESULTS = "🏆 Natijalarni kanalga e'lon qilish"
BTN_MISTAKES = "🎯 Xatolar ustida ishlash"
BTN_EXPLANATIONS = "💡 Yechimlar / Izohlar"
BTN_LINK_PARENT = "👨‍👩‍👧 Ota-ona / Repetitorni ulash"
BTN_WEBAPP_SOLVE = "📱 Ekranda yechish (Mini App)"
BTN_FEEDBACK = "✍️ Taklif va Muammo"



# ======================================================================
#  RO'YXATDAN O'TISH
# ======================================================================

WELCOME_NEW = (
    "🎓 <b>TestLab</b>\n"
    f"{LINE}\n\n"
    "Testlarni <b>bir necha soniyada</b> yarating va tekshiring.\n\n"
    "👨‍🏫 <b>O'qituvchilar uchun</b>\n"
    "   Test varaqasi rasmini tashlang va javoblar kalitini yozing —\n"
    "   test tayyor.\n\n"
    "🎓 <b>O'quvchilar uchun</b>\n"
    "   Test raqamini yuboring, javoblaringizni yozing —\n"
    "   natijani darhol ko'ring.\n\n"
    "Boshlash uchun ro'yxatdan o'ting 👇"
)

ASK_FULL_NAME = (
    "🪪 <b>Ro'yxatdan o'tish</b>\n"
    f"{LINE}\n\n"
    "Iltimos, <b>ism va familiyangizni</b> to'liq kiriting:\n\n"
    "📌 <b>Nega bu muhim?</b>\n"
    "Ism va familiyangiz rasmiy <b>sertifikat, diplom, reyting va o'qituvchi hisoboti</b>da "
    "aynan siz kiritganingizdek aks etadi. Shuning uchun laqab (nikneym) yoki qisqartma yozmaslikni so'raymiz.\n\n"
    "💡 <i>Namuna:</i> <b>Ali Valiyev</b> yoki <b>Aziza Karimova Akmal qizi</b>\n\n"
    "<i>(Telefon raqam kiritish talab etilmaydi)</i>"
)

FULL_NAME_INVALID = (
    "⚠️ <b>Ism va familiyangizni to'liq kiriting!</b>\n"
    f"{LINE}\n\n"
    "Sertifikat va natijalar ro'yxatida to'g'ri chiqishi uchun kamida 2 ta so'z (ism va familiya) bo'lishi kerak.\n\n"
    "Faqat harflar, apostrof va defisdan foydalaning (raqam yoki belgilarsiz).\n\n"
    "💡 <i>Namuna:</i> <b>Ali Valiyev</b>"
)

ONE_WORD_NAME = (
    "⚠️ <b>Faqat bitta so'z kiritildi!</b>\n"
    f"{LINE}\n\n"
    "Siz faqat ismingizni kiritdingiz. Sertifikat va hisobotda to'liq ko'rinishi uchun familiyangizni ham yozing.\n\n"
    "💡 <i>Namuna:</i> <b>Ali Valiyev</b>"
)

NAME_TOO_SHORT = "⚠️ Juda qisqa. Kamida 5 ta harf yozing."
NAME_TOO_LONG = "⚠️ Juda uzun. Ko'pi bilan 80 ta belgi."
SEND_TEXT_PLEASE = "⚠️ Iltimos, <b>matn</b> yuboring."


def registered(user: User) -> str:
    return (
        "✅ <b>Ro'yxatdan o'tdingiz!</b>\n"
        f"{LINE}\n\n"
        f"👤 {escape(user.full_name)}\n"
        f"{user.role_title}\n\n"
        "Endi testga javob berishingiz mumkin.\n"
        "Test raqamini shunchaki yozing — masalan <code>1</code>"
    )


# ======================================================================
#  BOSH MENYU
# ======================================================================

def main_menu(user: User, stats: dict) -> str:
    lines = [
        "🎓 <b>TestLab</b>",
        LINE,
        "",
        f"👤 {escape(user.full_name)}",
        f"{user.role_title}   ·   ⚡️ {user.xp} XP",
    ]

    if stats.get("total"):
        lines += [
            "",
            f"📊 Yechilgan testlar: <b>{stats['total']}</b>",
            f"📈 O'rtacha natija: <b>{stats['average']:g}%</b>",
            f"🥇 Eng yaxshi: <b>{stats['best']:g}%</b>",
        ]
    else:
        lines += ["", "<i>Hali test yechmagansiz.</i>"]

    lines += [
        "",
        LINE,
        "💡 Test raqamini shunchaki yozing: <code>1</code>",
    ]

    if user.is_teacher:
        lines.append("💡 Test yaratish: <code>Nom+abcdabcd</code>")

    return "\n".join(lines)


HELP = (
    "❓ <b>Yordam</b>\n"
    f"{LINE}\n\n"
    "<b>Testga javob berish — 3 usul:</b>\n\n"
    "1️⃣ Test raqamini yozing:\n"
    "     <code>12</code>\n\n"
    "2️⃣ Raqam va javoblarni birga:\n"
    "     <code>12*abcdabcd</code>\n\n"
    "3️⃣ «✅ Testga javob berish» tugmasi orqali\n\n"
    f"{LINE}\n\n"
    "<b>Test yaratish (o'qituvchilar):</b>\n\n"
    "1️⃣ Bitta xabarda:\n"
    "     <code>Matematika+abcdabcd</code>\n\n"
    "2️⃣ Rasm bilan:\n"
    "     «➕ Test yaratish» → rasm → kalit\n\n"
    f"{LINE}\n\n"
    "✅ Katta va kichik harf farqi yo'q\n"
    "✅ Bo'shliq, vergul qo'ysangiz ham bo'ladi\n"
    "❗️ Bilmagan savol o'rniga <code>-</code> qo'ying"
)


# ======================================================================
#  TEST YARATISH
# ======================================================================

HOW_TO_CREATE_TEXT = (
    "📖 <b>TEST YARATISH BO'YICHA YO'RIQNOMA</b>\n"
    f"{LINE}\n\n"
    "Botda test yaratishning <b>2 xil qulay usuli</b> bor:\n\n"
    "🔹 <b>1-USUL: Fayl yoki Rasm bilan yaratish (Tavsiya etiladi)</b>\n"
    "<b>1.</b> Menyudagi <b>«➕ Test yaratish»</b> tugmasini bosing yoki <code>/new</code> yuboring.\n"
    "<b>2.</b> Test varaqasi rasmi, <b>PDF</b> yoki <b>Word (DOC, DOCX)</b> faylini yuboring.\n"
    "   <i>💡 Faylga izoh (caption) yozsangiz — u test nomi bo'ladi.</i>\n"
    "<b>3.</b> Javoblar kalitini yuboring (masalan: <code>abcdabcd</code> yoki <code>1a2b3c4d</code>).\n\n"
    "⚡️ <b>2-USUL: Bitta xabarda tezkor yaratish</b>\n"
    "Test nomi va kalitini <code>+</code> bilan ajratib bitta xabarda yuborasiz:\n"
    "   • <code>Matematika 10-sinf+abcdabcd</code>\n"
    "   • <code>Fizika Blok-1+1a2b3c4d</code>\n\n"
    "💡 <b>Qulayliklar:</b>\n"
    "• Kalitdagi harflar soni avtomatik ravishda savollar sonini aniqlaydi.\n"
    "• Kirill harflari (а, в, с) avtomatik lotinlashtiriladi.\n"
    "• Javobsiz qoldirilgan savol o'rniga <code>-</code> belgisini qo'yishingiz mumkin."
)


CREATE_START = (
    "📁 <b>FAYLLI / RASMLI TEST YARATISH</b>\n"
    f"{LINE}\n\n"
    "<b>1.</b> Test varaqasi rasmi yoki fayli (Rasm, PDF, Word <code>.doc</code>/<code>.docx</code>) yuboring\n"
    "<b>2.</b> Javoblar kalitini yozing\n\n"
    "Tamom — test tayyor bo'ladi.\n\n"
    "💡 Bir nechta fayl/rasm bo'lsa ketma-ket yuboring.\n"
    "💡 Faylga izoh yozsangiz — test nomi bo'ladi."
)


def photo_added(count: int) -> str:
    return (
        f"✅ <b>{count}-fayl/rasm qabul qilindi</b>\n\n"
        "Yana fayl yuboring, yoki <b>javoblar kalitini</b> yozing:\n\n"
        "<code>abcdabcd</code>   yoki   <code>1a2b3c4d</code>"
    )


PHOTO_DUPLICATE = "⚠️ Bu fayl allaqachon qo'shilgan — o'tkazib yuborildi."

NOT_A_PHOTO = (
    "⚠️ Qo'llab-quvvatlanmaydigan fayl formati.\n\n"
    "Test varaqasini <b>rasm</b>, <b>PDF</b> yoki <b>Word (DOC, DOCX)</b> "
    "hujjat ko'rinishida yuboring."
)

NO_PHOTO_YET = (
    "⚠️ <b>Avval test fayli yoki rasmini yuboring.</b>\n\n"
    "Kalitni fayldan keyin yozasiz."
)


def test_published(test: Test, bot_username: str, media_count: int) -> str:
    """E'lon qilingandan keyin — ulashishga tayyor xabar (kalitsiz)."""
    timer_info = f"⏱ Vaqt: <b>{test.time_limit_sec // 60} daqiqa</b>\n" if test.time_limit_sec > 0 else ""
    return (
        "✅ <b>Test ishlanishga tayyor!</b>\n"
        f"{LINE}\n\n"
        f"📝 Test nomi: <b>{escape(test.title)}</b>\n"
        f"📊 Savollar soni: <b>{test.questions_count} ta</b>\n"
        + (f"🖼 Fayl/Rasmlar: <b>{media_count} ta</b>\n" if media_count else "")
        + f"🔑 Test kodi: <b>{test.number}</b>\n"
        + timer_info
        + f"👤 Test yaratuvchisi: {escape(test.author_name)}\n\n"
        f"{LINE}\n"
        f"📌 Testda qatnashish uchun @{bot_username} ga kirib "
        f"<b>{test.number}</b> sonini yuboring."
    )


# ======================================================================
#  TEST YECHISH
# ======================================================================

def test_card(test: Test, media_count: int) -> str:
    """
    Test kartochkasi — rasmlardan KEYIN yuboriladi.

    Ilgari kartochka rasmdan oldin, ko'rsatma esa keyin yuborilardi —
    rasm ikki xabar orasida qolib ketardi. Endi: rasmlar, so'ng bitta
    xabar. U tugma bosilganda joyida o'zgaradi.
    """
    return (
        f"📝 <b>{escape(test.title)}</b>\n"
        f"{LINE}\n\n"
        f"🔑 Test kodi: <b>{test.number}</b>\n"
        f"📊 Savollar soni: <b>{test.questions_count} ta</b>\n"
        + (f"🖼 Rasmlar: <b>{media_count} ta</b>\n" if media_count else "")
        + f"👤 Test yaratuvchisi: {escape(test.author_name)}\n"
        f"🎯 O'tish balli: <b>{test.pass_score}%</b>\n"
        f"❗️ Urinishlar: <b>{'cheksiz' if test.max_attempts == 0 else test.max_attempts}</b>\n"
        #  Vaqt HAQIQATAN sanaladi — o'quvchi buni oldindan bilishi shart
        + (
            f"⏳ Vaqt: <b>{fmt_duration(test.time_limit_sec)}</b> "
            f"<i>(hozir boshlandi)</i>\n"
            if test.time_limit_sec > 0 else ""
        )
        + "\n"
        + (
            "Yuqoridagi rasmlarni ko'rib, savollarni yeching.\n\n"
            if media_count else ""
        )
        + "Tayyor bo'lsangiz 👇"
    )


def ask_answers(test: Test) -> str:
    """
    Javob so'rovi — kartochka SHU MATNGA aylanadi (yangi xabar emas).

    Namuna aynan shu testning savollar soniga moslanadi: o'quvchi
    nechta harf yozish kerakligini ko'rib turadi.
    """
    count = test.questions_count
    example = "".join("abcd"[index % 4] for index in range(min(count, 8)))
    tail = "…" if count > 8 else ""

    return (
        "📨 <b>JAVOBLARNI YUBORING</b>\n"
        f"{LINE}\n\n"
        f"📝 <b>{escape(test.title)}</b>\n"
        f"📊 Savollar: <b>{count} ta</b>\n\n"
        f"Javoblaringizni <b>bitta xabarda</b> yuboring — "
        f"<b>{count} ta harf</b>:\n\n"
        f"<code>{example}{tail}</code>\n\n"
        f"<i>Boshqa ko'rinishlar ham bo'ladi:</i>\n"
        f"<code>1a2b3c4d…</code>   ·   <code>{test.number}*{example}{tail}</code>\n\n"
        f"{LINE}\n"
        "⚠️ Bilmagan savolingiz o'rniga <code>-</code> qo'ying\n"
        "✅ Katta/kichik harf farqi yo'q\n"
        "❗️ Har bir testga faqat <b>bir marta</b> javob berish mumkin"
    )


TEST_NOT_FOUND = (
    "⚠️ <b>Test topilmadi.</b>\n\n"
    "Test raqamini tekshirib, qaytadan yuboring.\n"
    "<i>Raqamni o'qituvchingizdan oling.</i>"
)

SENDING_IMAGES = "🖼 Test rasmlari yuborilmoqda..."
NO_IMAGES = "⚠️ Bu testda rasmlar yo'q."


# ======================================================================
#  NATIJA
# ======================================================================

#  Shu sondan ko'p savol bo'lsa — faqat XATOLARNI ko'rsatamiz.
#
#  Nega chegara kerak? Har bir savol ~30 belgi. Telegram xabari
#  4096 belgi bilan cheklangan, ya'ni ~130 savoldan keyin xabar
#  UMUMAN yuborilmaydi. Bundan tashqari 50 ta "✅ to'g'ri" qatorini
#  o'qishning ma'nosi ham yo'q — o'quvchiga XATOLARI kerak.
COMPACT_THRESHOLD = 25

#  Xatolar ro'yxatiga ham chegara: 200 savolli testda HAMMASI xato
#  bo'lsa, faqat xatolarni ko'rsatish ham 8000+ belgi beradi.
#  Qolganini "va yana N ta" deb yakunlaymiz — batafsili Excel'da.
MAX_MISTAKES_SHOWN = 40


def result(submit, *, hide_keys: bool = False) -> str:
    """
    Savolma-savol natija.

    `hide_keys=True` bo'lsa (masalan test hali davom etayotganda yoki muddat tugamaguncha),
    savollarning to'g'ri kalitlari ko'rsatilmaydi — faqat to'plangan ball va foiz ko'rsatiladi.

    `submit` — AssessmentService.SubmitResult
    """
    test = submit.test
    total = len(submit.questions) if submit.questions else (test.questions_count or 1)
    compact = total > COMPACT_THRESHOLD

    if getattr(submit, "is_disqualified", False):
        return (
            f"🚨 <b>Test qoidabuzarlik sababli bekor qilindi!</b>\n"
            f"{LINE}\n\n"
            f"📌 Test kodi: <b>{test.number}</b>\n"
            f"📝 Savollar soni: <b>{test.questions_count} ta</b>\n"
            f"👤 Test yaratuvchisi: {escape(test.author_name)}\n"
            f"⚠️ <b>Sabab:</b> Test jarayonida {getattr(submit, 'tab_switches_count', 0)} marta test oynasidan chiqildi.\n\n"
            f"📊 Natijangiz: <b>0 ball (Bekor qilingan)</b>\n"
            f"ℹ️ O'qituvchi hisobotiga belgi tushirildi."
        )

    lines = [
        f"📌 Test kodi: <b>{test.number}</b>",
        f"📝 Savollar soni: <b>{test.questions_count} ta</b>",
        f"👤 Test yaratuvchisi: {escape(test.author_name)}",
        "",
    ]

    if hide_keys:
        lines += [
            "🛡 <b>Anti-Cheat Himoyasi:</b>",
            "<i>To'g'ri kalitlar va savollar tahlili sir saqlanmoqda.</i>",
        ]
        if test.ends_at:
            from core.datetime_utils import fmt_datetime
            lines.append(
                f"🔒 <i>To'liq tahlil test muddati tugagach (<b>{fmt_datetime(test.ends_at)}</b>) ochiladi.</i>"
            )
        else:
            lines.append("🔒 <i>To'liq tahlil test yakunlangach ochiladi.</i>")
        lines.append("")
    elif compact:
        mistakes = [item for item in submit.questions if item.verdict is not True]

        if mistakes:
            lines.append(f"<b>Xatolar ({len(mistakes)} ta):</b>")

            for item in mistakes[:MAX_MISTAKES_SHOWN]:
                number = f"{item.number}."
                shown = item.given or "—"
                lines.append(
                    f"<code>{number:>4}</code> {shown} {item.icon}  to'g'risi: <b>{item.correct}</b>"
                )

            hidden = len(mistakes) - MAX_MISTAKES_SHOWN
            if hidden > 0:
                lines.append(f"<i>… va yana {hidden} ta xato</i>")
        else:
            lines.append("🎯 <b>Bitta ham xato yo'q!</b>")

        if submit.correct:
            lines.append("")
            lines.append(f"<i>Qolgan {submit.correct} ta savol to'g'ri yechilgan.</i>")

    else:
        lines.append("<b>Natijalari:</b>")
        for item in submit.questions:
            number = f"{item.number}."
            shown = item.given or "—"

            if item.verdict is True:
                lines.append(f"<code>{number:>4}</code> {shown} ✅   1 ball")
            else:
                lines.append(
                    f"<code>{number:>4}</code> {shown} {item.icon}({item.correct})   0 ball"
                )

    lines += [
        "",
        LINE,
        f"📊 Jami: <b>{submit.correct} ta ({submit.percentage:g}%)</b>",
    ]

    if submit.wrong:
        lines.append(f"❌ Xato: {submit.wrong} ta")
    if submit.skipped:
        lines.append(f"➖ Javobsiz: {submit.skipped} ta")

    lines.append(f"🏅 Baho: <b>{submit.grade}</b>")

    if submit.participants:
        lines.append(
            f"🏆 Reyting: <b>{submit.rank}-o'rin</b> ({submit.participants} ta)"
        )

    if submit.xp_earned:
        lines.append(f"⚡️ +{submit.xp_earned} XP")

    #  Seriya faqat o'sgan kunda ko'rsatiladi: har bir testda takrorlansa
    #  e'tibordan qolib, kunning yutug'i bo'lmay qoladi
    if submit.streak_grew and submit.streak >= 2:
        lines.append(f"🔥 <b>{submit.streak} kun ketma-ket!</b>")

    return "\n".join(lines)


# ======================================================================
#  MENING TESTLARIM
# ======================================================================

def my_tests_page(page, total: int) -> str:
    lines = [
        "📚 <b>MENING TESTLARIM</b>",
        LINE,
        "",
        f"Jami: <b>{total} ta</b>",
        "",
    ]

    if not page.items:
        lines.append("<i>Hali test yaratmagansiz.</i>\n")
        lines.append("💡 Bitta xabarda yarating: <code>Nom+abcdabcd</code>")
        return "\n".join(lines)

    for test in page.items:
        lines.append(
            f"<b>№{test.number}</b> · {escape(test.title)}\n"
            f"     {test.status_label} · {test.questions_count} savol · "
            f"👥 {test.attempts_count}"
        )

    if page.pages > 1:
        lines += ["", f"Sahifa <b>{page.page}/{page.pages}</b>"]

    return "\n".join(lines)


def test_manage(test: Test, media_count: int, participants: int) -> str:
    timer_str = f"⏱ Taymer: <b>{test.time_limit_sec // 60} daqiqa</b>" if test.time_limit_sec > 0 else "⏱ Taymer: <b>Cheksiz</b>"

    return (
        f"📝 <b>{escape(test.title)}</b>\n"
        f"{LINE}\n\n"
        f"🔑 Kod: <b>{test.number}</b>\n"
        f"{test.status_label}\n"
        f"📊 Savollar: <b>{test.questions_count} ta</b>\n"
        + (f"🖼 Fayl/Rasmlar: <b>{media_count} ta</b>\n" if media_count else "")
        + f"👥 Javob berganlar: <b>{participants} ta</b>\n"
        f"📈 O'rtacha: <b>{test.avg_score:g}%</b>\n"
        f"👁 Ko'rishlar: <b>{test.views}</b>\n"
        f"{timer_str}\n\n"
        "<b>Javoblar kaliti:</b>\n"
        f"{format_key(test.key_letters)}"
    )


# ======================================================================
#  JAVOB BERGANLAR
# ======================================================================

def participants_page(test: Test, page, start: int = 0) -> str:
    """
    Testni ishlaganlar ro'yxati (reyting tartibida).
    Format:
    1-test haqida ma'lumotlar

    📋Test nomi:  Matematika
    📝Test kodi: 1
    🔢Savollar soni: 30 ta
    👤Test yaratuvchisi: Saxobiddin Karimov
    Testda qatnashganlar soni: 39

    1. Ismoilov Suxrobjon 29 ball
    2. Shamshodbek Hamdamqulov 29 ball
    ...
    """
    questions_cnt = test.questions_count or (len(test.answer_key) if test.answer_key else 0)

    if test.author:
        if getattr(test.author, "telegram_id", None):
            author_str = f'<a href="tg://user?id={test.author.telegram_id}">{escape(test.author.full_name)}</a>'
        else:
            author_str = escape(test.author.full_name)
    else:
        author_str = "Noma'lum"

    header_test = f"{test.number}-test" if test.number else escape(test.title)

    lines = [
        f"{header_test} haqida ma'lumotlar",
        "",
        f"📋Test nomi:  {escape(test.title)}",
        f"📝Test kodi: {test.number or '—'}",
        f"🔢Savollar soni: {questions_cnt} ta",
        f"👤Test yaratuvchisi: {author_str}",
        f"Testda qatnashganlar soni: {page.total}",
        "",
    ]

    if page.is_empty:
        lines.append("<i>Hali hech kim test ishlamagan.</i>")
    else:
        for offset, attempt in enumerate(page.items, start=start + 1):
            name = escape(attempt.user.full_name) if attempt.user else "—"
            score = attempt.score if attempt.score is not None else attempt.correct_count
            lines.append(f"{offset}. {name} {score} ball")

    if page.pages > 1:
        lines += [
            "",
            f"📄 Sahifa: <b>{page.page}/{page.pages}</b>",
        ]

    return "\n".join(lines)


NOBODY_ANSWERED = "⚠️ Hali hech kim javob bermagan."
EXCEL_BUILDING = "📊 Excel jadval tayyorlanmoqda..."

#  Bitta sahifadagi savollar soni. Telegram chegarasi 4096 belgi;
#  har bir savol qatori ~60 belgi, sarlavha bilan birga 25 ta xavfsiz
#  sig'adi. 200 savolli test 8 sahifaga bo'linadi.
ANALYSIS_PER_PAGE = 25

#  Ogohlantirishlar ro'yxati cheklanadi: 200 savolli testda 40 ta
#  «juda qiyin» savol bo'lsa, hammasini sanash xabarni ham buzadi,
#  o'qituvchining diqqatini ham tarqatadi.
MAX_SUSPECTS_SHOWN = 3
MAX_HARDEST_SHOWN = 3


def analysis_pages(rows: list) -> int:
    """Tahlil necha sahifaga bo'linadi."""
    if not rows:
        return 1
    return max(1, -(-len(rows) // ANALYSIS_PER_PAGE))


def question_analysis(
    test: Test,
    rows: list,
    participants: int,
    page: int = 1,
) -> str:
    """
    Savolma-savol tahlil — o'qituvchi uchun.

    Ilgari bu ma'lumot faqat Excel faylida bor edi: o'qituvchi jadvalni
    yuklab, ochib, varaqni almashtirishi kerak edi. Eng kerakli javob
    («qaysi savol qiyin bo'ldi?») shu qadar uzoq bo'lmasligi kerak.

    `rows` — `AssessmentService.question_breakdown()` natijasi.
    """
    lines = [
        "📈 <b>SAVOLLAR TAHLILI</b>",
        LINE,
        "",
        f"📝 <b>{escape(test.title)}</b>",
        f"👥 Ishtirokchilar: <b>{participants} ta</b>",
    ]

    if not rows or participants == 0:
        lines += ["", "<i>Hali hech kim javob bermagan — tahlil qilishga "
                      "ma'lumot yo'q.</i>"]
        return "\n".join(lines)

    total_pages = analysis_pages(rows)
    page = max(1, min(page, total_pages))

    #  --- Ogohlantirishlar faqat 1-sahifada ---
    #  Ular butun testga tegishli, har sahifada takrorlansa e'tibordan
    #  qoladi va joyni egallaydi.
    if page == 1:
        suspects = [row for row in rows if row["suspect_key"]]

        if suspects:
            lines += ["", "⚠️ <b>KALITNI TEKSHIRING</b>"]

            for row in suspects[:MAX_SUSPECTS_SHOWN]:
                share = round(row["top_wrong_count"] / participants * 100)
                lines.append(
                    f"   <b>{row['number']}-savol</b>: kalitda "
                    f"<b>{row['correct_letter']}</b>, lekin {share}% "
                    f"o'quvchi <b>{row['top_wrong']}</b> deb belgilagan."
                )

            hidden = len(suspects) - MAX_SUSPECTS_SHOWN
            if hidden > 0:
                lines.append(f"   <i>… va yana {hidden} ta shunday savol</i>")

        hardest = sorted(rows, key=lambda row: (row["rate"], row["number"]))
        hardest = [row for row in hardest if row["rate"] < 0.5][:MAX_HARDEST_SHOWN]

        if hardest:
            listed = ", ".join(
                f"{row['number']}-savol ({row['rate']:.0%})" for row in hardest
            )
            lines += ["", f"🔻 <b>Eng qiyinlari:</b> {listed}"]

    # --- Savollar ro'yxati ---
    start = (page - 1) * ANALYSIS_PER_PAGE
    chunk = rows[start:start + ANALYSIS_PER_PAGE]

    lines += ["", LINE, ""]

    for row in chunk:
        number = f"{row['number']}."
        rate = f"{row['rate']:.0%}"
        mark = "⚠️" if row["suspect_key"] else _rate_icon(row["rate"])

        line = (
            f"<code>{number:>4}</code> {row['correct_letter']} "
            f"{mark} <b>{rate}</b> ({row['correct']}/{participants})"
        )

        #  Chalg'ituvchi variant faqat u sezilarli bo'lsa ko'rsatiladi:
        #  bitta odamning tasodifiy xatosi ma'lumot emas, shovqin.
        if row["top_wrong"] and row["top_wrong_count"] > 1:
            line += f" · ko'p: {row['top_wrong']}×{row['top_wrong_count']}"

        lines.append(line)

    if total_pages > 1:
        lines += ["", f"Sahifa <b>{page}/{total_pages}</b>"]

    return "\n".join(lines)


def _rate_icon(rate: float) -> str:
    """Savol muvaffaqiyatining bir belgili ko'rinishi."""
    if rate >= 0.8:
        return "🟢"
    if rate >= 0.5:
        return "🟡"
    return "🔴"


def excel_caption(test: Test, participants: int) -> str:
    return (
        f"📊 <b>{escape(test.title)}</b> — natijalar\n\n"
        f"🔑 Test kodi: <b>{test.number}</b>\n"
        f"👥 Ishtirokchilar: <b>{participants} ta</b>\n\n"
        "<b>Jadvalda:</b>\n"
        "  1-varaq — kim nechchi ball to'plagani\n"
        "  2-varaq — qaysi savol qiyin bo'lgani"
    )


# ======================================================================
#  NATIJALARIM VA REYTING
# ======================================================================

def my_results(page) -> str:
    lines = ["📊 <b>NATIJALARIM</b>", LINE, ""]

    if page.is_empty:
        lines.append("<i>Hali test yechmagansiz.</i>\n")
        lines.append("💡 Test raqamini yozing: <code>1</code>")
        return "\n".join(lines)

    lines.append(f"Jami: <b>{page.total} ta</b>\n")

    for attempt in page.items:
        title = escape(attempt.test.title) if attempt.test else "—"
        mark = "✅" if attempt.is_passed else "❌"
        lines.append(
            f"{mark} <b>{title}</b>\n"
            f"     {attempt.percentage:g}% · {attempt.grade or '—'} · "
            f"{fmt_datetime(attempt.finished_at)}"
        )

    if page.pages > 1:
        lines += ["", f"Sahifa <b>{page.page}/{page.pages}</b>"]

    lines += ["", "💡 <i>Batafsil tahlil va yechimlarni ko'rish uchun kerakli testni tanlang:</i>"]

    return "\n".join(lines)


def attempt_detail_text(attempt, explanations: dict | None = None) -> str:
    test = attempt.test
    title = escape(test.title if test else f"Test #{attempt.test_id}")
    author = escape(test.author_name if test else "—")
    date_str = fmt_datetime(attempt.finished_at)
    mark = "✅ O'tdi" if attempt.is_passed else "❌ O'tmadi"

    lines = [
        "📊 <b>TEST TAHLILI VA NATIJALARI</b>",
        LINE,
        "",
        f"📝 <b>Test:</b> {title} (№{test.number if test else attempt.test_id})",
        f"👨‍🏫 <b>Muallif:</b> {author}",
        f"📅 <b>Vaqti:</b> {date_str}",
        f"🎯 <b>Natija:</b> <b>{attempt.score}/{attempt.max_score}</b> ({attempt.percentage:g}%) · {attempt.grade or '—'}",
        f"🏁 <b>Holati:</b> {mark}",
        "",
        "📋 <b>SAVOLMA-SAVOL TAHLIL:</b>",
        LINE,
    ]

    sub_key = (attempt.submitted_key or "").upper()
    ans_key = (test.answer_key or "").upper() if test else ""
    q_count = max(len(ans_key), len(sub_key), attempt.max_score)
    expl_map = explanations or {}

    for i in range(1, q_count + 1):
        my_ans = sub_key[i - 1] if i - 1 < len(sub_key) else "-"
        correct_ans = ans_key[i - 1] if i - 1 < len(ans_key) else "?"
        has_expl = i in expl_map or 0 in expl_map
        expl_badge = " · 💡 [Yechimi bor]" if has_expl else ""

        if my_ans == "-":
            status_icon = "⚪️"
            detail = f"Javobsiz (to'g'risi: <b>{correct_ans}</b>)"
        elif my_ans == correct_ans:
            status_icon = "✅"
            detail = f"Siz: <b>{my_ans}</b> (to'g'ri)"
        else:
            status_icon = "❌"
            detail = f"Siz: <b>{my_ans}</b> | To'g'ri: <b>{correct_ans}</b>"

        lines.append(f"{status_icon} <b>#{i:02d}:</b> {detail}{expl_badge}")

    lines.append("")
    lines.append("💡 <i>Savollarning to'liq yechimlari va tushuntirishlarini ko'rish uchun quyidagi tugmani bosing:</i>")

    return "\n".join(lines)


def leaderboard(users: list[User], me: User, my_rank: int) -> str:
    lines = ["🏆 <b>UMUMIY REYTING</b>", LINE, ""]

    if not users:
        lines.append("<i>Reyting hali bo'sh.</i>")
        return "\n".join(lines)

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for position, user in enumerate(users, start=1):
        medal = medals.get(position, f"<code>{position:>2}.</code>")
        mark = " ← <b>siz</b>" if user.id == me.id else ""
        lines.append(f"{medal} {escape(user.short_name)} — {user.xp} XP{mark}")

    if my_rank > len(users):
        lines += ["", LINE, f"Sizning o'rningiz: <b>{my_rank}</b> · {me.xp} XP"]

    return "\n".join(lines)


def personal_ranking(user: User, rank: int, total_users: int, stats: dict) -> str:
    """Foydalanuvchining faqat o'ziga tegishli shaxsiy reytingi va ko'rsatkichlari."""
    medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else "🏆"))
    pct_text = f"{stats['average']:g}%" if stats.get("total", 0) > 0 else "—"
    best_text = f"{stats['best']:g}%" if stats.get("total", 0) > 0 else "—"

    if user.xp >= 1000:
        tier = "👑 Afsonaviy Bilimdon"
    elif user.xp >= 500:
        tier = "💎 Ekspert"
    elif user.xp >= 200:
        tier = "🥇 Usta O'quvchi"
    elif user.xp >= 50:
        tier = "🥈 Faol O'quvchi"
    else:
        tier = "🥉 Boshlang'ich O'quvchi"

    lines = [
        f"{medal} <b>SIZNING SHAXSIY REYTINGINGIZ</b>",
        LINE,
        "",
        f"👤 <b>Foydalanuvchi:</b> {escape(user.full_name)}",
        f"🎖 <b>Darajangiz:</b> {tier}",
        "",
        f"🏅 <b>Umumiy o'rningiz:</b> <b>{rank}-o'rin</b> (jami {max(1, total_users)} ta o'quvchi orasida)",
        f"⚡️ <b>To'plangan tajriba (XP):</b> <b>{user.xp} XP</b>",
        "",
        "📊 <b>Natijalaringiz:</b>",
        f"• 📝 Yechilgan testlar: <b>{stats.get('total', 0)} ta</b>",
        f"• ✅ Muvaffaqiyatli: <b>{stats.get('passed', 0)} ta</b>",
        f"• 📈 O'rtacha aniqlik: <b>{pct_text}</b>",
        f"• 🥇 Eng yuqori natija: <b>{best_text}</b>",
        "",
        "<i>💡 Har bir to'g'ri ishlangan test sizga yangi XP ballari beradi va o'rningizni ko'taradi!</i>",
    ]
    return "\n".join(lines)


def profile(user: User, stats: dict, rank: int) -> str:
    return (
        "👤 <b>PROFIL</b>\n"
        f"{LINE}\n\n"
        f"<b>{escape(user.full_name)}</b>\n"
        f"{user.role_title}\n"
        + (f"📱 {escape(user.phone)}\n" if user.phone else "")
        + (f"🔗 @{escape(user.username)}\n" if user.username else "")
        + "\n"
        f"⚡️ XP: <b>{user.xp}</b>   ·   🏆 O'rin: <b>{rank}</b>\n\n"
        f"📊 Yechilgan testlar: <b>{stats['total']}</b>\n"
        f"✅ O'tganlari: <b>{stats['passed']}</b>\n"
        f"📈 O'rtacha: <b>{stats['average']:g}%</b>\n"
        f"🥇 Eng yaxshi: <b>{stats['best']:g}%</b>\n\n"
        f"📅 Ro'yxatdan o'tgan: {fmt_datetime(user.created_at)}"
    )


# ======================================================================
#  ADMIN
# ======================================================================

def admin_dashboard(users: dict, tests: dict, attempts: dict) -> str:
    return (
        "🛠 <b>ADMIN PANEL</b>\n"
        f"{LINE}\n\n"
        "<b>👥 Foydalanuvchilar</b>\n"
        f"     Jami: <b>{users['total']}</b>   ·   "
        f"Ro'yxatdan o'tgan: <b>{users['registered']}</b>\n"
        f"     Bugun faol: <b>{users['active_today']}</b>   ·   "
        f"Hafta: <b>{users['active_week']}</b>\n"
        f"     O'qituvchilar: <b>{users['teachers']}</b>   ·   "
        f"Bloklangan: <b>{users['banned']}</b>\n\n"
        "<b>📝 Testlar</b>\n"
        f"     Jami: <b>{tests['total']}</b>   ·   "
        f"Ochiq: <b>{tests['published']}</b>   ·   "
        f"Qoralama: <b>{tests['drafts']}</b>\n\n"
        "<b>✍️ Javoblar</b>\n"
        f"     Jami: <b>{attempts['total']}</b>   ·   "
        f"Ishtirokchilar: <b>{attempts['participants']}</b>\n"
        f"     O'rtacha natija: <b>{attempts['average']:g}%</b>"
    )


def admin_users_page(page, title: str) -> str:
    lines = [f"👥 <b>{title}</b>", LINE, "", f"Jami: <b>{page.total} ta</b>", ""]

    if page.is_empty:
        lines.append("<i>Topilmadi.</i>")
        return "\n".join(lines)

    for offset, user in enumerate(page.items, start=page.start_index + 1):
        marks = []
        if user.is_banned:
            marks.append("🚫")
        if user.is_admin:
            marks.append("⚙️")
        elif user.is_teacher:
            marks.append("👨‍🏫")

        lines.append(
            f"<code>{offset:>3}.</code> <b>{escape(user.full_name)}</b> "
            f"{''.join(marks)}\n"
            f"      ⚡️ {user.xp} XP · "
            f"{('@' + escape(user.username)) if user.username else 'ID ' + str(user.telegram_id)}"
        )

    if page.pages > 1:
        lines += ["", f"Sahifa <b>{page.page}/{page.pages}</b>"]

    return "\n".join(lines)


def admin_solvers_page(page, period_label: str) -> str:
    lines = [
        "✍️ <b>TEST YECHGANLAR</b>",
        LINE,
        "",
        f"📅 {period_label}",
        f"Jami: <b>{page.total} ta topshiriq</b>",
        "",
    ]

    if page.is_empty:
        lines.append("<i>Bu davrda hech kim javob bermagan.</i>")
        return "\n".join(lines)

    for offset, attempt in enumerate(page.items, start=page.start_index + 1):
        name = escape(attempt.user.full_name) if attempt.user else "—"
        test_title = escape(attempt.test.title) if attempt.test else "—"
        mark = "✅" if attempt.is_passed else "❌"

        lines.append(
            f"<code>{offset:>3}.</code> <b>{name}</b>\n"
            f"      {test_title} · {attempt.percentage:g}% {mark}"
        )

    if page.pages > 1:
        lines += ["", f"Sahifa <b>{page.page}/{page.pages}</b>"]

    lines += ["", f"💡 To'liq ma'lumot: «{BTN_EXCEL}»"]
    return "\n".join(lines)


def admin_user_card(user: User, stats: dict) -> str:
    lines = [
        "👤 <b>FOYDALANUVCHI</b>",
        LINE,
        "",
        f"<b>{escape(user.full_name)}</b>",
        f"{user.role_title}",
        "",
        f"🆔 <code>{user.telegram_id}</code>",
    ]

    if user.username:
        lines.append(f"🔗 @{escape(user.username)}")
    if user.phone:
        lines.append(f"📱 {escape(user.phone)}")

    lines += [
        "",
        f"⚡️ XP: <b>{user.xp}</b>",
        f"📊 Yechilgan: <b>{stats['total']}</b> · O'rtacha: <b>{stats['average']:g}%</b>",
        "",
        f"📅 Qo'shilgan: {fmt_datetime(user.created_at)}",
        f"🕐 Oxirgi faollik: {fmt_datetime(user.last_active_at)}",
    ]

    if user.is_banned:
        lines += ["", "🚫 <b>BLOKLANGAN</b>"]
        if user.ban_reason:
            lines.append(f"<i>Sabab: {escape(user.ban_reason)}</i>")

    return "\n".join(lines)


ADMIN_ASK_SEARCH = (
    "🔍 <b>QIDIRUV</b>\n"
    f"{LINE}\n\n"
    "Ism, familiya, username, telefon yoki Telegram ID yozing:"
)


# ======================================================================
#  O'QITUVCHI HUQUQI
# ======================================================================

BTN_REQUEST_TEACHER = "📩 Ruxsat so'rash"
BTN_GRANT_TEACHER = "👨‍🏫 O'qituvchi qilish"

TEACHER_ONLY = (
    "👨‍🏫 <b>O'QITUVCHI BO'LING</b>\n"
    f"{LINE}\n\n"
    "Test yaratish — <b>o'qituvchilar</b> uchun imkoniyat.\n\n"
    "<b>O'qituvchi sifatida siz:</b>\n\n"
    "📸  Varaqa rasmini tashlaysiz va kalitni yozasiz — test tayyor\n"
    "⚡️  Yoki bitta qatorda: <code>Matematika+abcdabcd</code>\n"
    "👥  Kim javob berganini va nechchi ball olganini ko'rasiz\n"
    "📊  Natijalarni Excel jadval qilib yuklab olasiz\n"
    "📈  Qaysi savol qiyin bo'lganini bilib olasiz\n"
    "🏆  O'quvchilaringiz reytingini kuzatasiz\n\n"
    f"{LINE}\n\n"
    "Ruxsat olish uchun administratorga <b>so'rov yuboring</b> 👇"
)

REQUEST_SENT = (
    "✅ <b>So'rovingiz yuborildi!</b>\n"
    f"{LINE}\n\n"
    "Administrator ko'rib chiqadi va tez orada javob beradi.\n\n"
    "<i>Ruxsat berilgach sizga xabar keladi — shundan so'ng\n"
    "test yaratishingiz mumkin bo'ladi.</i>"
)

REQUEST_ALREADY_SENT = (
    "⏳ <b>So'rovingiz allaqachon yuborilgan.</b>\n\n"
    "Administrator ko'rib chiqmoqda — biroz kuting."
)

TEACHER_GRANTED = (
    "🎉 <b>Tabriklaymiz!</b>\n"
    f"{LINE}\n\n"
    "Sizga <b>o'qituvchi</b> huquqi berildi.\n\n"
    "Endi test yaratishingiz mumkin:\n\n"
    "1️⃣ Bitta qatorda:\n"
    "     <code>Matematika+abcdabcd</code>\n\n"
    "2️⃣ Rasm bilan:\n"
    "     «➕ Test yaratish» → rasm → kalit\n\n"
    "Omad! 🚀"
)


def teacher_request_for_admin(user: User) -> str:
    """Adminga keladigan so'rov xabari."""
    lines = [
        "📩 <b>O'QITUVCHI HUQUQI SO'RALDI</b>",
        LINE,
        "",
        f"👤 <b>{escape(user.full_name)}</b>",
        f"🆔 <code>{user.telegram_id}</code>",
    ]

    if user.username:
        lines.append(f"🔗 @{escape(user.username)}")
    if user.phone:
        lines.append(f"📱 {escape(user.phone)}")

    lines += [
        "",
        f"⚡️ XP: <b>{user.xp}</b>",
        f"📅 Qo'shilgan: {fmt_datetime(user.created_at)}",
        "",
        "<i>Ruxsat berish uchun pastdagi tugmani bosing.</i>",
    ]

    return "\n".join(lines)


# ======================================================================
#  JADVAL BILDIRISHNOMALARI (fon vazifasi)
# ======================================================================

def attempt_expired(test: Test) -> str:
    """O'quvchiga: testni ochgan edingiz, vaqt tugadi."""
    return (
        "⏳ <b>VAQT TUGADI</b>\n"
        f"{LINE}\n\n"
        f"<b>№{test.number}</b> · {escape(test.title)}\n\n"
        "Testni ochgan edingiz, lekin javoblaringiz belgilangan\n"
        "vaqt ichida yetib kelmadi. Urinish <b>0 ball</b> bilan yopildi.\n\n"
        "<i>Yangi urinish qolgan bo'lsa, testni qaytadan ochishingiz "
        "mumkin.</i>"
    )


def test_auto_opened(test: Test) -> str:
    """Muallifga: jadval bo'yicha test ochildi."""
    return (
        "⏰ <b>TEST OCHILDI</b>\n"
        f"{LINE}\n\n"
        f"<b>№{test.number}</b> · {escape(test.title)}\n\n"
        "Belgilangan vaqt keldi — test yechish uchun ochiq.\n\n"
        f"<i>O'quvchilar botga <code>{test.number}</code> deb yozib "
        f"kirishlari mumkin.</i>"
    )


def test_auto_closed(test: Test) -> str:
    """Muallifga: muddat tugadi, test arxivlandi."""
    return (
        "📦 <b>TEST YOPILDI</b>\n"
        f"{LINE}\n\n"
        f"<b>№{test.number}</b> · {escape(test.title)}\n\n"
        f"Muddati tugadi ({fmt_datetime(test.ends_at)}) — test arxivga\n"
        "o'tkazildi va yangi javoblar qabul qilinmaydi.\n\n"
        f"👥 Jami yechganlar: <b>{test.attempts_count} ta</b>\n"
        f"📊 O'rtacha natija: <b>{test.avg_score:g}%</b>"
    )


# ======================================================================
#  OMMAVIY XABAR
# ======================================================================

BTN_BROADCAST = "📣 Ommaviy xabar"
BTN_BROADCAST_SEND = "🚀 Yuborish"
BTN_BROADCAST_ALL = "👥 Hammaga"
BTN_BROADCAST_TEACHERS = "👨‍🏫 O'qituvchilarga"

BROADCAST_ASK = (
    "📣 <b>OMMAVIY XABAR</b>\n"
    f"{LINE}\n\n"
    "Yubormoqchi bo'lgan xabarni <b>shu yerga tashlang</b>.\n\n"
    "Matn, rasm, video, fayl — hammasi bo'ladi. Xabar qanday\n"
    "ko'rinishda yuborilsa, o'quvchilarga ham shundayligicha boradi.\n\n"
    "<i>Bekor qilish uchun /cancel</i>"
)

BROADCAST_EMPTY = (
    "⚠️ <b>Qabul qiluvchi yo'q.</b>\n\n"
    "Bildirishnomani yoqqan foydalanuvchi topilmadi."
)

BROADCAST_SENDING = "📣 Yuborilmoqda..."
BROADCAST_CANCELLED = "✖️ Ommaviy xabar bekor qilindi."


def broadcast_preview(total: int, audience: str) -> str:
    """Tasdiqdan oldingi ekran. Xabarning o'zi alohida yuboriladi."""
    return (
        "📣 <b>YUBORISHNI TASDIQLANG</b>\n"
        f"{LINE}\n\n"
        "Yuqoridagi xabar aynan shu ko'rinishda boradi.\n\n"
        f"👥 Qabul qiluvchilar: <b>{total} ta</b>  ({audience})\n"
        f"⏱ Taxminiy vaqt: <b>{_broadcast_eta(total)}</b>\n\n"
        "⚠️ <b>Yuborilgan xabarni orqaga qaytarib bo'lmaydi.</b>"
    )


def _broadcast_eta(total: int) -> str:
    """
    Yuborish qancha davom etishi.

    Telegram sekundiga ~30 xabarga ruxsat beradi; biz xavfsizlik
    uchun sekinroq yuboramiz. Admin 20 000 kishilik ro'yxat 20
    daqiqa ketishini OLDINDAN bilishi kerak.
    """
    from core.datetime_utils import fmt_duration

    if total <= 0:
        return "—"

    return fmt_duration(max(1, round(total / 20)))


def broadcast_progress(sent: int, total: int) -> str:
    percent = round(sent / total * 100) if total else 0
    return (
        "📣 <b>YUBORILMOQDA</b>\n"
        f"{LINE}\n\n"
        f"{sent} / {total}  ({percent}%)"
    )


def broadcast_done(sent: int, failed: int, seconds: float) -> str:
    from core.datetime_utils import fmt_duration

    lines = [
        "✅ <b>OMMAVIY XABAR YUBORILDI</b>",
        LINE,
        "",
        f"📨 Yetkazildi: <b>{sent} ta</b>",
    ]

    if failed:
        lines.append(f"🚫 Yetkazilmadi: <b>{failed} ta</b>")
        lines.append(
            "<i>Ko'pincha bu botni bloklagan yoki hisobini o'chirgan\n"
            "foydalanuvchilar.</i>"
        )

    lines += ["", f"⏱ Vaqt: {fmt_duration(seconds)}"]
    return "\n".join(lines)


# ======================================================================
#  MAJBURIY OBUNA
# ======================================================================

BTN_CHECK_SUBSCRIPTION = "✅ Obunani tekshirish"

SUBSCRIPTION_SHORT = "📢 Avval kanallarga a'zo bo'ling."
SUBSCRIPTION_STILL_MISSING = (
    "❌ Hali hamma kanalga a'zo bo'lmadingiz.\n\n"
    "Kanallarga kiring va qaytadan tekshiring."
)


def channel_link(channel: str) -> str | None:
    """
    Kanal havolasi. Raqamli ID uchun havola tuzib bo'lmaydi — None.

    Yopiq kanalning ID'si berilgan bo'lsa, foydalanuvchiga havola
    ko'rsatolmaymiz: unday kanalga faqat taklif havolasi bilan
    kiriladi va uni administrator o'zi tarqatadi.
    """
    clean = channel.strip()

    if clean.startswith("https://") or clean.startswith("t.me/"):
        return clean if clean.startswith("https://") else f"https://{clean}"

    if clean.startswith("@"):
        return f"https://t.me/{clean[1:]}"

    #  Raqamli ID (-100...) yoki tushunarsiz qiymat
    if clean.lstrip("-").isdigit():
        return None

    return f"https://t.me/{clean}"


def channel_label(channel: str) -> str:
    """Ro'yxatda ko'rinadigan nom."""
    clean = channel.strip()

    if clean.startswith("@"):
        return clean
    if clean.lstrip("-").isdigit():
        return "Yopiq kanal"

    return f"@{clean.rsplit('/', 1)[-1]}"


def subscription_required(channels: list[str]) -> str:
    """Obuna talab qilinadigan ekran."""
    lines = [
        "📢 <b>KANALGA A'ZO BO'LING</b>",
        LINE,
        "",
        "Botdan foydalanish uchun quyidagi kanallarga\n"
        "a'zo bo'lishingiz kerak:",
        "",
    ]

    for channel in channels:
        lines.append(f"   • {escape(channel_label(channel))}")

    lines += [
        "",
        LINE,
        "",
        f"A'zo bo'lgach «{BTN_CHECK_SUBSCRIPTION}» tugmasini bosing.",
    ]

    return "\n".join(lines)


SUBSCRIPTION_OK = (
    "✅ <b>Rahmat!</b>\n\n"
    "Endi botdan to'liq foydalanishingiz mumkin."
)


# ======================================================================
#  UMUMIY XATOLAR
# ======================================================================

NOT_FOUND = "⚠️ Topilmadi."
NO_PERMISSION = "🔒 Sizda bunga ruxsat yo'q."
SESSION_EXPIRED = (
    "⏳ <b>Sessiya eskirdi.</b>\n\n"
    "Iltimos, qaytadan boshlang."
)
BANNED = (
    "🚫 <b>Hisobingiz bloklangan.</b>\n\n"
    "Administratorga murojaat qiling."
)
TOO_FAST = "⏳ Juda tez yozyapsiz. Biroz kuting."
CANCELLED = "✖️ <b>Bekor qilindi.</b>"


def unknown_error(error_id: str) -> str:
    return (
        "❌ <b>Kutilmagan xatolik</b>\n"
        f"{LINE}\n\n"
        "Xatolik yuz berdi va administratorlarga xabar berildi.\n\n"
        f"<i>Xato kodi: <code>{error_id}</code></i>\n\n"
        "Iltimos, /start bosib qaytadan urinib ko'ring."
    )


FALLBACK = (
    "🤔 <b>Tushunmadim.</b>\n\n"
    "Test raqamini yozing (masalan <code>1</code>) "
    "yoki pastdagi tugmalardan foydalaning."
)


# ======================================================================
#  SERTIFIKAT
# ======================================================================

BTN_CERTIFICATE = "🏆 Sertifikat olish"
BTN_MY_CERTIFICATES = "🏅 Sertifikatlarim"

CERTIFICATE_BUILDING = "🏆 Sertifikat tayyorlanmoqda..."


def certificate_caption(certificate) -> str:
    """Sertifikat rasmi ostidagi izoh."""
    from modules.certification.service import motivation_title

    return (
        f"🏆 <b>SERTIFIKAT BERILDI</b>\n"
        f"{LINE}\n\n"
        f"📝 {escape(certificate.test_title)}\n"
        f"📊 Natija: <b>{certificate.percentage:g}%</b> · "
        f"Baho: <b>{certificate.grade}</b>\n"
        f"🏅 Reyting: <b>{certificate.rank}/{certificate.total_participants}</b>\n\n"
        f"<b>{motivation_title(certificate.percentage)}</b>\n\n"
        f"🔍 № <code>{certificate.serial}</code>\n"
        f"<i>QR kod orqali haqiqiyligini tekshirish mumkin.</i>\n\n"
        f"🚀 <b>Keyingi test sizni kutmoqda!</b>"
    )


def certificate_verified(certificate) -> str:
    """QR kod skanerlanganda ko'rinadigan matn."""
    return (
        f"✅ <b>SERTIFIKAT HAQIQIY</b>\n"
        f"{LINE}\n\n"
        f"👤 Egasi: <b>{escape(certificate.holder_name)}</b>\n"
        f"📝 Test: {escape(certificate.test_title)}\n"
        f"📊 Natija: <b>{certificate.percentage:g}%</b> · "
        f"Baho: <b>{certificate.grade}</b>\n"
        f"🏅 Reyting: {certificate.rank}/{certificate.total_participants}\n"
        f"📅 Berilgan: {fmt_datetime(certificate.issued_at)}\n\n"
        f"🔍 № <code>{certificate.serial}</code>"
    )


# ======================================================================
#  O'QITUVCHIGA BILDIRISHNOMA
# ======================================================================

def teacher_notification(submit, student) -> str:
    """
    Kimdir testga javob berdi — muallifga xabar.

    Qisqa bo'lishi kerak: o'qituvchi kuniga o'nlab shunday xabar
    olishi mumkin.
    """
    mark = "✅" if submit.passed else "❌"

    return (
        f"{mark} <b>Yangi javob</b>\n\n"
        f"👤 {escape(student.full_name)}\n"
        f"📝 {escape(submit.test.title)} (№{submit.test.number})\n"
        f"📊 <b>{submit.percentage:g}%</b> · {submit.correct}/{submit.attempt.max_score} · "
        f"{submit.grade}\n"
        f"🏆 {submit.rank}-o'rin ({submit.participants} ta)"
    )


# ======================================================================
#  DEEP LINK
# ======================================================================

DEEP_LINK_NOT_FOUND = (
    "⚠️ <b>Havola eskirgan.</b>\n\n"
    "Test o'chirilgan yoki yopilgan bo'lishi mumkin."
)


# ======================================================================
#  KANAL / GURUHGA ULASHISH VA NATIJALAR
# ======================================================================

ASK_CHANNEL_TARGET = (
    "📢 <b>Testni kanal yoki guruhga ulashish</b>\n"
    f"{LINE}\n\n"
    "Test e'lon qilinishi kerak bo'lgan kanal yoki guruhni yuboring:\n\n"
    "1️⃣ Kanal username'ini yozing: masalan <code>@mening_kanalim</code>\n"
    "2️⃣ Yoki o'sha kanaldan ixtiyoriy xabarni bu yerga <b>Forward</b> (uzatish) qiling.\n\n"
    "⚠️ <b>Muhim:</b> Bot ushbu kanal/guruhda <b>Administrator</b> bo'lishi va xabar yozish huquqiga ega bo'lishi shart!"
)

CHANNEL_NOT_ADMIN = (
    "❌ <b>Bot kanalda administrator emas yoki xabar yozish huquqi yo'q!</b>\n\n"
    "Iltimos, botni kanalga/guruhga qo'shib, unga <b>admin</b> huquqini bering va qaytadan urinib ko'ring."
)

CHANNEL_POST_SUCCESS = (
    "✅ <b>Test kanalga muvaffaqiyatli joylandi!</b>\n\n"
    "O'quvchilar havola orqali botga kirib testni yechishlari mumkin. "
    "Test muddati tugagach yoki yopilganda g'oliblar reytingi (Top-10) avtomatik e'lon qilinadi."
)

NO_PARTICIPANTS_YET = (
    "⚠️ <b>Hozircha hech kim javob bermagan.</b>\n\n"
    "Natijalarni e'lon qilish uchun kamida bitta ishtirokchi testni topshirgan bo'lishi kerak."
)

CHANNEL_RESULTS_POSTED = "✅ <b>Natijalar kanalga muvaffaqiyatli e'lon qilindi!</b>"


def channel_test_post(test: Test, bot_username: str) -> str:
    """Kanalga chiqariladigan test posteri matni."""
    questions_cnt = len(test.answer_key) if test.answer_key else 0
    timer_str = f"{test.time_limit_sec // 60} daqiqa" if test.time_limit_sec > 0 else "Cheklanmagan"
    deadline_str = fmt_datetime(test.ends_at) if test.ends_at else "Belgilanmagan"

    return (
        f"🎯 <b>YANGI TEST E'LON QILINDI!</b>\n"
        f"{LINE}\n\n"
        f"📝 <b>Fan / Mavzu:</b> {escape(test.title)}\n"
        f"🔢 <b>Test kodi:</b> <code>{test.number}</code>\n"
        f"❓ <b>Savollar soni:</b> {questions_cnt} ta\n"
        f"⏱ <b>Vaqt chegarasi:</b> {timer_str}\n"
        f"⏳ <b>Yakunlanish vaqti:</b> {deadline_str}\n\n"
        f"💡 Testda qatnashish va natijangizni bilish uchun pastdagi havola tugmasini bosing 👇"
    )


def channel_leaderboard(test: Test, attempts: list[Attempt], total_count: int) -> str:
    """Kanalga chiqariladigan yakuniy natijalar va g'oliblar reytingi (Top-10)."""
    questions_cnt = len(test.answer_key) if test.answer_key else 0
    lines = [
        "🏁 <b>TEST YAKUNLANDI VA NATIJALAR E'LON QILINDI!</b>",
        LINE,
        "",
        f"📝 <b>Fan / Mavzu:</b> {escape(test.title)}",
        f"🔢 <b>Test kodi:</b> <code>{test.number}</code>",
        f"❓ <b>Savollar soni:</b> {questions_cnt} ta",
        f"👥 <b>Jami ishtirokchilar:</b> {total_count} ta",
        "",
        "🏆 <b>TOP-10 G'OLIBLAR RO'YXATI:</b>",
        "",
    ]

    if not attempts:
        lines.append("<i>Testda hech kim qatnashmadi.</i>")
        return "\n".join(lines)

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for rank, attempt in enumerate(attempts[:10], start=1):
        name = escape(attempt.user.full_name) if attempt.user else "Noma'lum"
        medal = medals.get(rank, f"<code>{rank:>2}.</code>")
        score_info = f"{attempt.percentage:g}% ({attempt.correct_count}/{attempt.max_score})"
        dur_str = f" · ⏱ {fmt_duration(attempt.duration_sec)}" if attempt.duration_sec else ""
        lines.append(f"{medal} <b>{name}</b> — {score_info}{dur_str}")

    lines += [
        "",
        LINE,
        "👏 Barcha ishtirokchilarga tashakkur!",
        "🚀 O'z sertifikatingiz va batafsil natijalaringizni botda ko'rishingiz mumkin.",
    ]
    return "\n".join(lines)


# ======================================================================
#  OTA-ONA / REPETITORGA BILDIRISHNOMA
# ======================================================================

PARENT_LINK_ALREADY = "ℹ️ Siz allaqachon ushbu o'quvchiga ulangansiz."


def parent_notification(submit, student: User) -> str:
    """Ota-onaga yoki repetitorga avtomatik natija xabari."""
    mark = "✅ O'tdi" if submit.passed else "❌ O'tmadi"
    dur_str = f" · ⏱ {fmt_duration(submit.attempt.duration_sec)}" if submit.attempt.duration_sec else ""

    return (
        f"👨‍👩‍👧 <b>FARZANDINGIZ NATIJASI</b>\n"
        f"{LINE}\n\n"
        f"👤 <b>O'quvchi:</b> {escape(student.full_name)}\n"
        f"📝 <b>Test:</b> {escape(submit.test.title)} (№{submit.test.number})\n"
        f"📊 <b>Natija:</b> <b>{submit.percentage:g}%</b> ({submit.correct}/{submit.attempt.max_score})\n"
        f"🏅 <b>Baho:</b> {submit.grade} ({mark})\n"
        f"🏆 <b>O'rin:</b> {submit.rank}-o'rin ({submit.participants} ta ichida){dur_str}\n\n"
        f"💡 <i>Farzandingiz bilimini doimiy qo'llab-quvvatlab boring!</i>"
    )


def parent_linked_msg(student_name: str) -> str:
    return (
        f"✅ <b>Muvaffaqiyatli ulandingiz!</b>\n"
        f"{LINE}\n\n"
        f"Siz <b>{escape(student_name)}</b> ning ota-onasi / repetitori sifatida qayd etildingiz.\n"
        f"Endi har safar o'quvchi test yechganda uning bahosi va foizi sizga avtomatik yetkaziladi."
    )


def parent_hub_text(link_url: str, parents: list) -> str:
    lines = [
        "👨‍👩‍👧 <b>OTA-ONA / REPETITORGA AVTO-HISOBOT</b>",
        LINE,
        "",
        "Har safar test yechganingizda, natijangiz ota-onangiz yoki ustozingizga "
        "avtomatik ravishda chiroyli bildirishnoma bo'lib boradi.",
        "",
        "🔗 <b>Ulanish uchun havolangiz:</b>",
        f"<code>{link_url}</code>",
        "",
        "<i>Ushbu havolani ota-onangiz yoki repetitoringizga yuboring. Ular ustiga bosishlari kifoya.</i>",
        "",
    ]
    if parents:
        lines.append("👥 <b>Ulangan nazoratchilar:</b>")
        for p in parents:
            pname = escape(p.parent_name or f"ID {p.parent_telegram_id}")
            lines.append(f"  • {pname} ({p.relationship_type})")
    else:
        lines.append("<i>Hozircha hech kim ulanmagan.</i>")
    return "\n".join(lines)


# ======================================================================
#  XATOLAR USTIDA ISHLASH
# ======================================================================

def mistakes_hub_text(mistakes: list) -> str:
    count = len(mistakes)
    lines = [
        "🎯 <b>XATOLAR USTIDA ISHLASH</b>",
        LINE,
        "",
        f"Sizda <b>{count} ta</b> tuzatilmagan xato savollar mavjud.",
        "",
    ]
    if not mistakes:
        lines.append("🎉 <i>Ajoyib! Xatolar daftaringiz hozircha bo'sh. Barcha testlarni a'lo yechyapsiz!</i>")
        return "\n".join(lines)

    tests_map = {}
    for m in mistakes:
        t_title = m.test.title if m.test else f"Test #{m.test_id}"
        tests_map[t_title] = tests_map.get(t_title, 0) + 1

    lines.append("📚 <b>Mavzular bo'yicha xatolar:</b>")
    for t_name, cnt in list(tests_map.items())[:5]:
        lines.append(f"  • {escape(t_name)}: <b>{cnt} ta</b> xato")
    if len(tests_map) > 5:
        lines.append(f"  va yana {len(tests_map) - 5} ta mavzu...")

    lines += [
        "",
        "💡 <i>«Qayta ishlash» tugmasini bossangiz, bot aynan adashgan savollaringizdan "
        "shaxsiy qayta test tuzib beradi.</i>"
    ]
    return "\n".join(lines)


# ======================================================================
#  SAVOLLAR YECHIMLARI VA TUSHUNTIRISHLAR
# ======================================================================

def explanation_view_text(test: Test, q_num: int, explanation, my_mistake=None) -> str:
    lines = [
        f"💡 <b>{q_num}-SAVOL YECHIMI VA TUSHUNTIRISHI</b>",
        LINE,
        f"📝 <b>Test:</b> {escape(test.title)} (№{test.number})",
    ]
    if my_mistake:
        lines.append(f"❌ Siz tanlagan javob: <b>{my_mistake.given_answer}</b>")
        lines.append(f"✅ To'g'ri javob: <b>{my_mistake.correct_answer}</b>")
    elif test.answer_key and q_num <= len(test.answer_key):
        lines.append(f"✅ To'g'ri javob: <b>{test.answer_key[q_num - 1].upper()}</b>")

    lines += [
        "",
        "📖 <b>Yechim:</b>",
        escape(explanation.explanation_text if explanation else "Ushbu savol uchun hali izoh kiritilmagan."),
    ]
    return "\n".join(lines)


# ======================================================================
#  TAKLIF VA MUAMMO (FEEDBACK)
# ======================================================================

FEEDBACK_PROMPT = (
    "✍️ <b>TAKLIF VA MUAMMO</b>\n"
    f"{LINE}\n\n"
    "Botni yanada qulay va foydali qilish bo'yicha <b>taklifingiz</b> yoki biror "
    "<b>xatolik / kamchilikka</b> duch kelgan bo'lsangiz, uni batafsil yozib yuboring.\n\n"
    "📷 <i>Skrinshot yoki rasm bilan ham yuborishingiz mumkin.</i>\n\n"
    "Bekor qilish: /cancel"
)

FEEDBACK_SENT = (
    "✅ <b>Murojaatingiz ma'muriyatga yetkazildi!</b>\n\n"
    "Loyiha rivojiga befarq bo'lmaganingiz uchun tashakkur. "
    "Zarur bo'lsa, mutasaddilar tez orada siz bilan bog'lanishadi."
)


def feedback_admin_notification(user: User, text: str | None = None, has_media: bool = False) -> str:
    lines = [
        "📩 <b>YANGI TAKLIF / MUAMMO</b>",
        LINE,
        f"👤 <b>Foydalanuvchi:</b> {escape(user.full_name)}",
        f"🎭 <b>Roli:</b> {user.role_title}",
        f"🆔 <b>ID:</b> <code>{user.telegram_id}</code>",
    ]
    if user.username:
        lines.append(f"🔗 <b>Username:</b> @{user.username}")
    if user.phone:
        lines.append(f"📱 <b>Telefon:</b> {user.phone}")
    lines.append("")
    if has_media:
        lines.append("📎 <i>Foydalanuvchi rasm / fayl ilova qildi.</i>")
    if text:
        lines += [
            "💬 <b>Murojaat matni:</b>",
            f"«<i>{escape(text)}</i>»",
        ]
    lines += [
        "",
        LINE,
        "💡 <i>Quyidagi tugma orqali foydalanuvchiga to'g'ridan-to'g'ri javob yozishingiz mumkin.</i>",
    ]
    return "\n".join(lines)


def feedback_user_reply(reply_text: str) -> str:
    return (
        "👨‍💻 <b>ADMINISTRATOR JAVOBI</b>\n"
        f"{LINE}\n\n"
        f"{escape(reply_text)}\n\n"
        f"{LINE}\n"
        "<i>TestLab platformasidan foydalanganingiz uchun rahmat!</i>"
    )



