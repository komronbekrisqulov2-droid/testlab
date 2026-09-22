"""
Admin panel klaviaturalari.

Asosiy talab: admin uchta narsani BIR NECHA TUGMADA olishi kerak —
foydalanuvchilar, test yechganlar, reytinglar. Har biri botda ro'yxat
va Excel ko'rinishida.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from apps.bot.keyboards.callbacks import AdminCB, MenuCB
from apps.bot.keyboards.inline import back_button, home_button, pagination_row
from apps.bot.texts import uz
from core.config import settings
from core.security.permissions import Role
from infrastructure.database.repository import Page
from modules.identity.models import User

#  Davr filtrlari: (kun, yorliq)
PERIODS: tuple[tuple[int, str], ...] = (
    (1, "Bugun"),
    (7, "7 kun"),
    (30, "30 kun"),
    (0, "Butun davr"),
)


def period_label(days: int) -> str:
    for value, label in PERIODS:
        if value == days:
            return label
    return "Butun davr"


def panel_keyboard() -> InlineKeyboardMarkup:
    """Admin paneli — asosiy ekran."""
    builder = InlineKeyboardBuilder()

    #  Eng ko'p kerak bo'ladigan uchtasi tepada
    builder.row(
        InlineKeyboardButton(
            text="👥 Foydalanuvchilar",
            callback_data=AdminCB(action="users", page=1).pack(),
        ),
        InlineKeyboardButton(
            text="✍️ Test yechganlar",
            callback_data=AdminCB(action="solvers", page=1, period=7).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🏆 Reytinglar",
            callback_data=AdminCB(action="board").pack(),
        ),
        InlineKeyboardButton(
            text="📝 Testlar",
            callback_data=AdminCB(action="tests", page=1).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔍 Foydalanuvchi qidirish",
            callback_data=AdminCB(action="search").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_BROADCAST,
            callback_data=AdminCB(action="broadcast").pack(),
        )
    )

    webapp_icon = "🟢" if settings.webapp.enabled else "🔴"
    webapp_status = "Yoqilgan" if settings.webapp.enabled else "O'chirilgan"
    builder.row(
        InlineKeyboardButton(
            text=f"📱 Mini App: {webapp_icon} {webapp_status}",
            callback_data=AdminCB(action="toggle_webapp").pack(),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_REFRESH, callback_data=AdminCB(action="panel").pack()
        )
    )
    builder.row(home_button())
    return builder.as_markup()


def users_keyboard(page: Page) -> InlineKeyboardMarkup:
    """Foydalanuvchilar ro'yxati."""
    builder = InlineKeyboardBuilder()

    #  Har bir foydalanuvchi — alohida tugma
    for user in page.items:
        name = user.full_name[:26] + ("…" if len(user.full_name) > 26 else "")
        mark = "🚫 " if user.is_banned else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{mark}{name}",
                callback_data=AdminCB(
                    action="user", target_id=user.id, page=page.page
                ).pack(),
            )
        )

    row = pagination_row(
        page,
        lambda number: AdminCB(action="users", page=number).pack(),
    )
    if row:
        builder.row(*row)

    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_EXCEL,
            callback_data=AdminCB(action="excel_users").pack(),
        ),
        InlineKeyboardButton(
            text="🔍 Qidirish",
            callback_data=AdminCB(action="search").pack(),
        ),
    )
    builder.row(
        back_button(AdminCB(action="panel").pack()),
        home_button(),
    )
    return builder.as_markup()


def solvers_keyboard(page: Page, period: int) -> InlineKeyboardMarkup:
    """Test yechganlar ro'yxati — davr filtri bilan."""
    builder = InlineKeyboardBuilder()

    row = pagination_row(
        page,
        lambda number: AdminCB(action="solvers", page=number, period=period).pack(),
    )
    if row:
        builder.row(*row)

    #  Davr tanlash — faol bo'lgani belgilanadi
    period_buttons = [
        InlineKeyboardButton(
            text=("• " + label + " •") if value == period else label,
            callback_data=AdminCB(action="solvers", page=1, period=value).pack(),
        )
        for value, label in PERIODS
    ]
    builder.row(*period_buttons[:2])
    builder.row(*period_buttons[2:])

    if not page.is_empty:
        builder.row(
            InlineKeyboardButton(
                text=uz.BTN_EXCEL,
                callback_data=AdminCB(action="excel_solvers", period=period).pack(),
            )
        )

    builder.row(
        back_button(AdminCB(action="panel").pack()),
        home_button(),
    )
    return builder.as_markup()


def user_card_keyboard(user: User, page: int, *, is_super: bool = False) -> InlineKeyboardMarkup:
    """Bitta foydalanuvchi kartochkasi — boshqaruv tugmalari."""
    builder = InlineKeyboardBuilder()

    if user.is_banned:
        builder.row(
            InlineKeyboardButton(
                text="✅ Blokdan chiqarish",
                callback_data=AdminCB(action="unban", target_id=user.id, page=page).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🚫 Bloklash",
                callback_data=AdminCB(action="ban", target_id=user.id, page=page).pack(),
            )
        )

    # Rolni almashtirish tugmalari: O'quvchi / O'qituvchi / Admin
    role_buttons: list[InlineKeyboardButton] = []
    if user.role != Role.STUDENT.value:
        role_buttons.append(
            InlineKeyboardButton(
                text="🎓 O'quvchi qilish",
                callback_data=AdminCB(
                    action="role", target_id=user.id, page=page, period=0
                ).pack(),
            )
        )
    if user.role != Role.TEACHER.value:
        role_buttons.append(
            InlineKeyboardButton(
                text="👨‍🏫 O'qituvchi qilish",
                callback_data=AdminCB(
                    action="role", target_id=user.id, page=page, period=1
                ).pack(),
            )
        )
    # Faqat super admin boshqalarni admin yoki super admin qila oladi
    if is_super:
        if user.role != Role.ADMIN.value and user.role != Role.SUPER_ADMIN.value:
            role_buttons.append(
                InlineKeyboardButton(
                    text="🛠 Admin qilish",
                    callback_data=AdminCB(
                        action="role", target_id=user.id, page=page, period=2
                    ).pack(),
                )
            )
        if user.role != Role.SUPER_ADMIN.value:
            role_buttons.append(
                InlineKeyboardButton(
                    text="👑 Super Admin qilish",
                    callback_data=AdminCB(
                        action="role", target_id=user.id, page=page, period=3
                    ).pack(),
                )
            )

    if role_buttons:
        for i in range(0, len(role_buttons), 2):
            builder.row(*role_buttons[i:i + 2])

    builder.row(
        back_button(AdminCB(action="users", page=page).pack()),
        home_button(),
    )
    return builder.as_markup()


def board_keyboard() -> InlineKeyboardMarkup:
    """Reytinglar ekrani."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_REFRESH, callback_data=AdminCB(action="board").pack()
        )
    )
    builder.row(
        back_button(AdminCB(action="panel").pack()),
        home_button(),
    )
    return builder.as_markup()


def tests_keyboard(page: Page) -> InlineKeyboardMarkup:
    """Barcha testlar ro'yxati."""
    from apps.bot.keyboards.callbacks import PeopleCB

    builder = InlineKeyboardBuilder()

    for test in page.items:
        title = test.title[:24] + ("…" if len(test.title) > 24 else "")
        builder.row(
            InlineKeyboardButton(
                text=f"№{test.number} · {title} ({test.attempts_count})",
                callback_data=PeopleCB(action="list", test_id=test.id, page=1).pack(),
            )
        )

    row = pagination_row(
        page,
        lambda number: AdminCB(action="tests", page=number).pack(),
    )
    if row:
        builder.row(*row)

    builder.row(
        back_button(AdminCB(action="panel").pack()),
        home_button(),
    )
    return builder.as_markup()


def cancel_search_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_CANCEL, callback_data=AdminCB(action="panel").pack()
        )
    )
    return builder.as_markup()


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """
    Yuborishni tasdiqlash.

    Tasdiq va bekor qilish ATAYLAB alohida qatorlarda: ommaviy xabarni
    orqaga qaytarib bo'lmaydi, shuning uchun «Yuborish» ga tasodifan
    tegib ketish qiyin bo'lishi kerak.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_BROADCAST_SEND,
            callback_data=AdminCB(action="broadcast_go").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_CANCEL, callback_data=AdminCB(action="panel").pack()
        )
    )
    return builder.as_markup()


def broadcast_audience_keyboard() -> InlineKeyboardMarkup:
    """Kimga yuborilsin."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=uz.BTN_BROADCAST_ALL,
            callback_data=AdminCB(action="broadcast_ask", target_id=0).pack(),
        ),
        InlineKeyboardButton(
            text=uz.BTN_BROADCAST_TEACHERS,
            callback_data=AdminCB(action="broadcast_ask", target_id=1).pack(),
        ),
    )
    builder.row(
        back_button(AdminCB(action="panel").pack()),
        home_button(),
    )
    return builder.as_markup()
