"""
Rollar va huquqlar (RBAC).

Asosiy tamoyil: kod **rolni emas, HUQUQNI** tekshiradi.

    ❌  if user.role == "teacher": ...
    ✅  if user.can(Permission.TEST_CREATE): ...

Farqi shundaki, ertaga "Moderator ham test yaratsin" desangiz, faqat
quyidagi jadval o'zgaradi — handler'lar teginilmaydi. Rolni tekshiradigan
kodda esa o'nlab joyni qidirib chiqish kerak bo'lardi.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Foydalanuvchi roli. Tartib muhim: pastdan yuqoriga huquq oshadi."""

    GUEST = "guest"            # ro'yxatdan o'tmagan
    STUDENT = "student"        # oddiy foydalanuvchi
    TEACHER = "teacher"        # test yarata oladi
    MODERATOR = "moderator"    # kontentni nazorat qiladi
    ADMIN = "admin"            # foydalanuvchilarni boshqaradi
    SUPER_ADMIN = "super"      # hamma narsa


class Permission(StrEnum):
    """Aniq amallar."""

    # --- Test yechish ---
    TEST_SOLVE = "test.solve"
    TEST_VIEW_PUBLIC = "test.view_public"

    # --- Test yaratish ---
    TEST_CREATE = "test.create"
    TEST_EDIT_OWN = "test.edit_own"
    TEST_DELETE_OWN = "test.delete_own"
    TEST_EDIT_ANY = "test.edit_any"
    TEST_DELETE_ANY = "test.delete_any"

    # --- Natijalar ---
    RESULTS_VIEW_OWN = "results.view_own"
    RESULTS_VIEW_OWN_TESTS = "results.view_own_tests"   # o'z testlarini yechganlar
    RESULTS_VIEW_ANY = "results.view_any"
    RESULTS_EXPORT = "results.export"                   # Excel

    # --- Foydalanuvchilar ---
    USERS_VIEW = "users.view"
    USERS_SEARCH = "users.search"
    USERS_BAN = "users.ban"
    USERS_DELETE = "users.delete"
    USERS_SET_ROLE = "users.set_role"

    # --- Tizim ---
    ADMIN_PANEL = "admin.panel"
    ADMIN_BROADCAST = "admin.broadcast"
    ADMIN_LOGS = "admin.logs"
    ADMIN_SETTINGS = "admin.settings"


#  Har bir rol o'zidan oldingisining huquqlarini MEROS oladi.
#  Shu sababli jadvalda faqat QO'SHIMCHA huquqlar yoziladi —
#  takrorlash bo'lmaydi va bir joyni unutib qo'yish ehtimoli kamayadi.
_ROLE_CHAIN: tuple[Role, ...] = (
    Role.GUEST,
    Role.STUDENT,
    Role.TEACHER,
    Role.MODERATOR,
    Role.ADMIN,
    Role.SUPER_ADMIN,
)

_ADDED_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.GUEST: frozenset({
        Permission.TEST_VIEW_PUBLIC,
    }),
    Role.STUDENT: frozenset({
        Permission.TEST_SOLVE,
        Permission.RESULTS_VIEW_OWN,
    }),
    Role.TEACHER: frozenset({
        Permission.TEST_CREATE,
        Permission.TEST_EDIT_OWN,
        Permission.TEST_DELETE_OWN,
        Permission.RESULTS_VIEW_OWN_TESTS,
        Permission.RESULTS_EXPORT,
    }),
    Role.MODERATOR: frozenset({
        Permission.TEST_EDIT_ANY,
        Permission.USERS_VIEW,
        Permission.USERS_SEARCH,
    }),
    Role.ADMIN: frozenset({
        Permission.TEST_DELETE_ANY,
        Permission.RESULTS_VIEW_ANY,
        Permission.USERS_BAN,
        Permission.USERS_SET_ROLE,
        Permission.ADMIN_PANEL,
        Permission.ADMIN_BROADCAST,
        Permission.ADMIN_LOGS,
    }),
    Role.SUPER_ADMIN: frozenset({
        Permission.USERS_DELETE,
        Permission.ADMIN_SETTINGS,
    }),
}


def _build_matrix() -> dict[Role, frozenset[Permission]]:
    """Meros zanjirini yig'ib to'liq jadval yasaydi."""
    matrix: dict[Role, frozenset[Permission]] = {}
    accumulated: set[Permission] = set()

    for role in _ROLE_CHAIN:
        accumulated |= _ADDED_PERMISSIONS.get(role, frozenset())
        matrix[role] = frozenset(accumulated)

    return matrix


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = _build_matrix()


ROLE_LABELS: dict[Role, str] = {
    Role.GUEST: "👤 Mehmon",
    Role.STUDENT: "🎓 O'quvchi",
    Role.TEACHER: "👨‍🏫 O'qituvchi",
    Role.MODERATOR: "🛡 Moderator",
    Role.ADMIN: "⚙️ Admin",
    Role.SUPER_ADMIN: "👑 Super admin",
}


def has_permission(role: str | Role, permission: Permission) -> bool:
    """Shu roldagi foydalanuvchi bu amalni bajara oladimi?"""
    try:
        role_enum = Role(role)
    except ValueError:
        #  Bazada noma'lum rol turgan bo'lsa — eng past huquq beramiz.
        #  Bu xavfsizroq: noto'g'ri rol qo'shimcha huquq bermaydi.
        role_enum = Role.GUEST

    return permission in ROLE_PERMISSIONS[role_enum]


def permissions_of(role: str | Role) -> frozenset[Permission]:
    """Rolning barcha huquqlari."""
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return ROLE_PERMISSIONS[Role.GUEST]


def role_label(role: str | Role) -> str:
    """Rolning ko'rinadigan nomi."""
    try:
        return ROLE_LABELS[Role(role)]
    except ValueError:
        return "❔ Noma'lum"


def is_at_least(role: str | Role, minimum: Role) -> bool:
    """
    Rol kamida shu darajadami?

    Huquq tekshiruvi afzal, lekin ba'zan daraja solishtirish kerak
    bo'ladi — masalan "o'zidan yuqori rolni o'zgartira olmasin".
    """
    try:
        return _ROLE_CHAIN.index(Role(role)) >= _ROLE_CHAIN.index(minimum)
    except ValueError:
        return False
