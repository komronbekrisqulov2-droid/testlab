"""
Excel hisobotlari.

Fayl diskka YOZILMAYDI — xotirada yig'iladi va to'g'ridan-to'g'ri
Telegram'ga yuboriladi. Bu serverda axlat qoldirmaydi va bir vaqtda
bir nechta so'rov kelsa ham fayl nomi to'qnashmaydi.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.ext.asyncio import AsyncSession

from core.datetime_utils import fmt_datetime, to_local, utcnow
from core.logging import get_logger
from modules.assessment.models import Attempt
from modules.assessment.repository import AttemptRepository
from modules.assessment.service import AssessmentService
from modules.catalog.models import Test
from modules.identity.models import User

log = get_logger(__name__)


# ----------------------------------------------------------------------
#  Uslublar
# ----------------------------------------------------------------------

TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="1F3864")
SUBTITLE_FONT = Font(name="Calibri", size=10, color="595959")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
CELL_FONT = Font(name="Calibri", size=11)
MONO_FONT = Font(name="Consolas", size=10)

HEADER_FILL = PatternFill("solid", fgColor="2E5C9A")
PASS_FILL = PatternFill("solid", fgColor="E2EFDA")   # och yashil
FAIL_FILL = PatternFill("solid", fgColor="FCE4E4")   # och qizil

_thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")


@dataclass(slots=True, frozen=True)
class Column:
    """Jadval ustuni ta'rifi."""

    title: str
    width: int
    align: Alignment = CENTER


RESULT_COLUMNS: tuple[Column, ...] = (
    Column("№", 5),
    Column("Familiya, Ism", 28, LEFT),
    Column("Username", 18, LEFT),
    Column("Telefon", 16, LEFT),
    Column("Telegram ID", 14),
    Column("Ball", 9),
    Column("Foiz", 9),
    Column("Baho", 8),
    Column("To'g'ri", 9),
    Column("Xato", 8),
    Column("Javobsiz", 10),
    Column("Holat", 12),
    Column("Anti-cheat nazorati", 24, LEFT),
    Column("Javoblari", 34, LEFT),
    Column("Topshirgan vaqti", 19),
)

ANALYSIS_COLUMNS: tuple[Column, ...] = (
    Column("Savol №", 10),
    Column("To'g'ri javob", 14),
    Column("To'g'ri topganlar", 18),
    Column("Xato", 10),
    Column("Javobsiz", 11),
    Column("Muvaffaqiyat %", 16),
    #  Chalg'ituvchi variant: xato qilganlarning ko'pchiligi qaysi
    #  harfni tanlagan. «Savol qiyin» degandan foydaliroq — qaysi
    #  variant ishlaganini ko'rsatadi.
    Column("Ko'p tanlangan xato", 20),
    Column("Izoh", 22, LEFT),
)

USER_COLUMNS: tuple[Column, ...] = (
    Column("№", 5),
    Column("Familiya, Ism", 28, LEFT),
    Column("Username", 18, LEFT),
    Column("Telefon", 16, LEFT),
    Column("Telegram ID", 14),
    Column("Rol", 14),
    Column("XP", 8),
    Column("Yechgan testlari", 16),
    Column("O'rtacha %", 12),
    Column("Holat", 12),
    Column("Qo'shilgan", 19),
    Column("Oxirgi faollik", 19),
)

SOLVER_COLUMNS: tuple[Column, ...] = (
    Column("№", 5),
    Column("Familiya, Ism", 26, LEFT),
    Column("Telefon", 16, LEFT),
    Column("Telegram ID", 14),
    Column("Test №", 9),
    Column("Test nomi", 30, LEFT),
    Column("Ball", 9),
    Column("Foiz", 9),
    Column("Baho", 8),
    Column("Holat", 12),
    Column("Javoblari", 32, LEFT),
    Column("Vaqti", 19),
)


# ----------------------------------------------------------------------
#  Umumiy yordamchilar
# ----------------------------------------------------------------------

def _write_header(
    sheet: Worksheet,
    columns: tuple[Column, ...],
    *,
    row: int,
) -> None:
    """Ustun sarlavhalarini yozadi va kengliklarni belgilaydi."""
    for index, column in enumerate(columns, start=1):
        cell = sheet.cell(row=row, column=index, value=column.title)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = BORDER
        sheet.column_dimensions[get_column_letter(index)].width = column.width

    sheet.row_dimensions[row].height = 20


def _write_title(
    sheet: Worksheet,
    title: str,
    subtitle: str,
    *,
    span: int,
) -> None:
    """Sahifa sarlavhasini yozadi."""
    sheet.cell(row=1, column=1, value=title).font = TITLE_FONT
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)

    sheet.cell(row=2, column=1, value=subtitle).font = SUBTITLE_FONT
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)

    sheet.row_dimensions[1].height = 22
    sheet.row_dimensions[2].height = 16


def _sanitize_cell_value(val: Any) -> Any:
    """Excel formula inyeksiyasidan (CWE-1236) himoya: agar matn '=' bilan boshlansa apostrof qo'shiladi."""
    if isinstance(val, str) and val.startswith("="):
        return f"'{val}"
    return val


def _write_row(
    sheet: Worksheet,
    columns: tuple[Column, ...],
    values: tuple,
    *,
    row: int,
    fill: PatternFill | None = None,
    mono_index: int | None = None,
    percent_index: int | None = None,
) -> None:
    """Bitta qatorni yozadi."""
    for index, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=index, value=_sanitize_cell_value(value))
        cell.font = MONO_FONT if index == mono_index else CELL_FONT
        cell.alignment = columns[index - 1].align
        cell.border = BORDER

        if fill is not None:
            cell.fill = fill
        if index == percent_index:
            cell.number_format = "0.0%"


def _safe_filename(stem: str) -> str:
    """Fayl nomidan xavfli belgilarni olib tashlaydi."""
    cleaned = "".join(
        char if char.isalnum() or char in " -_()" else "_" for char in stem
    ).strip()
    return cleaned[:60] or "hisobot"


def _today() -> str:
    return (to_local(utcnow()) or datetime.now()).strftime("%Y-%m-%d")


def _empty_note(sheet: Worksheet, row: int, text: str) -> None:
    sheet.cell(row=row, column=1, value=text).font = SUBTITLE_FONT


# ======================================================================
#  BITTA TEST BO'YICHA HISOBOT
# ======================================================================

class TestReportBuilder:
    """Bitta test natijalarini `.xlsx` qiladi."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.attempts = AttemptRepository(session)
        self.assessment = AssessmentService(session)

    def filename(self, test: Test) -> str:
        return f"{_safe_filename(test.title)} (№{test.number}) {_today()}.xlsx"

    async def build(self, test: Test) -> tuple[bytes, int]:
        """
        Returns:
            (fayl baytlari, ishtirokchilar soni)
        """
        attempts = await self.attempts.list_all_by_test(test.id)

        workbook = Workbook()

        sheet = workbook.active
        sheet.title = "Natijalar"
        self._results_sheet(sheet, test, attempts)

        analysis = workbook.create_sheet("Savollar tahlili")
        await self._analysis_sheet(analysis, test, attempts)

        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()

        log.info("Excel: test=№%s ishtirokchilar=%d", test.number, len(attempts))
        return buffer.getvalue(), len(attempts)

    def _results_sheet(
        self,
        sheet: Worksheet,
        test: Test,
        attempts: list[Attempt],
    ) -> None:
        span = len(RESULT_COLUMNS)

        _write_title(
            sheet,
            test.title,
            f"Test kodi: {test.number}   •   "
            f"Savollar: {test.questions_count} ta   •   "
            f"O'tish balli: {test.pass_score}%   •   "
            f"Ishtirokchilar: {len(attempts)} ta   •   "
            f"Hisobot: {fmt_datetime(utcnow())}",
            span=span,
        )

        header_row = 4
        _write_header(sheet, RESULT_COLUMNS, row=header_row)

        for order, attempt in enumerate(attempts, start=1):
            user = attempt.user
            switches = getattr(attempt, "tab_switches_count", 0)
            is_disq = getattr(attempt, "is_disqualified", False)

            if is_disq or switches >= 3:
                anti_cheat_text = f"🚨 Qoidabuzar ({switches} marta chiqdi - Bekor qilindi)"
            elif switches > 0:
                anti_cheat_text = f"🟡 Shubhali ({switches} marta chiqdi)"
            else:
                anti_cheat_text = "🟢 Halol (0)"

            status_text = "Bekor qilindi" if is_disq else ("O'tdi" if attempt.is_passed else "O'tmadi")

            _write_row(
                sheet,
                RESULT_COLUMNS,
                (
                    order,
                    user.full_name if user else "—",
                    f"@{user.username}" if user and user.username else "—",
                    user.phone if user and user.phone else "—",
                    user.telegram_id if user else "—",
                    f"{attempt.score}/{attempt.max_score}",
                    attempt.percentage / 100,
                    attempt.grade or "—",
                    attempt.correct_count,
                    attempt.wrong_count,
                    attempt.skipped_count,
                    status_text,
                    anti_cheat_text,
                    (attempt.submitted_key or "").upper() or "—",
                    fmt_datetime(attempt.finished_at),
                ),
                row=header_row + order,
                fill=FAIL_FILL if (is_disq or not attempt.is_passed) else PASS_FILL,
                mono_index=14,
                percent_index=7,
            )

        if attempts:
            sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
            sheet.auto_filter.ref = (
                f"A{header_row}:{get_column_letter(span)}{header_row + len(attempts)}"
            )
        else:
            _empty_note(sheet, header_row + 1, "Hali hech kim javob bermagan.")

    async def _analysis_sheet(
        self,
        sheet: Worksheet,
        test: Test,
        attempts: list[Attempt],
    ) -> None:
        """Qaysi savol qiyin bo'lgani — o'qituvchi uchun eng qimmatli ma'lumot."""
        span = len(ANALYSIS_COLUMNS)

        _write_title(
            sheet,
            "Savollar bo'yicha tahlil",
            f"{test.title}  •  {len(attempts)} ta ishtirokchi",
            span=span,
        )

        header_row = 4
        _write_header(sheet, ANALYSIS_COLUMNS, row=header_row)

        rows = await self.assessment.question_breakdown(test)

        for offset, item in enumerate(rows, start=1):
            row = header_row + offset
            rate = float(item["rate"])

            _write_row(
                sheet,
                ANALYSIS_COLUMNS,
                (
                    item["number"],
                    item["correct_letter"],
                    item["correct"],
                    item["wrong"],
                    item["skipped"],
                    rate,
                    (
                        f"{item['top_wrong']} ({item['top_wrong_count']})"
                        if item["top_wrong"] else "—"
                    ),
                    #  Kalit shubhali bo'lsa izoh o'rniga ogohlantirish:
                    #  o'qituvchi jadvalni ochganda darhol ko'rsin
                    "⚠️ KALITNI TEKSHIRING" if item["suspect_key"] else item["note"],
                ),
                row=row,
                percent_index=6,
            )

            #  Qiyin savollarni ajratib ko'rsatamiz
            cell = sheet.cell(row=row, column=6)
            if rate < 0.5:
                cell.fill = FAIL_FILL
            elif rate >= 0.8:
                cell.fill = PASS_FILL

        if rows:
            sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
        else:
            _empty_note(sheet, header_row + 1, "Tahlil uchun ma'lumot yo'q.")


# ======================================================================
#  ADMIN HISOBOTLARI
# ======================================================================

class AdminReportBuilder:
    """Admin paneli uchun hisobotlar."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.attempts = AttemptRepository(session)

    # ------------------------------------------------------------------
    #  Foydalanuvchilar
    # ------------------------------------------------------------------

    def users_filename(self) -> str:
        return f"Foydalanuvchilar {_today()}.xlsx"

    async def build_users(self, users: list[User]) -> tuple[bytes, int]:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Foydalanuvchilar"

        span = len(USER_COLUMNS)
        _write_title(
            sheet,
            "Foydalanuvchilar",
            f"Jami: {len(users)} ta   •   Hisobot: {fmt_datetime(utcnow())}",
            span=span,
        )

        header_row = 4
        _write_header(sheet, USER_COLUMNS, row=header_row)

        for order, user in enumerate(users, start=1):
            stats = await self.attempts.user_stats(user.id)

            _write_row(
                sheet,
                USER_COLUMNS,
                (
                    order,
                    user.full_name,
                    f"@{user.username}" if user.username else "—",
                    user.phone or "—",
                    user.telegram_id,
                    user.role_title,
                    user.xp,
                    stats["total"],
                    stats["average"],
                    "Bloklangan" if user.is_banned else "Faol",
                    fmt_datetime(user.created_at),
                    fmt_datetime(user.last_active_at),
                ),
                row=header_row + order,
                fill=FAIL_FILL if user.is_banned else None,
            )

        if users:
            sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
            sheet.auto_filter.ref = (
                f"A{header_row}:{get_column_letter(span)}{header_row + len(users)}"
            )
        else:
            _empty_note(sheet, header_row + 1, "Foydalanuvchi yo'q.")

        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()

        log.info("Excel: foydalanuvchilar=%d", len(users))
        return buffer.getvalue(), len(users)

    # ------------------------------------------------------------------
    #  Test yechganlar
    # ------------------------------------------------------------------

    def solvers_filename(self, period_label: str) -> str:
        return f"Test yechganlar ({_safe_filename(period_label)}) {_today()}.xlsx"

    async def build_solvers(
        self,
        attempts: list[Attempt],
        *,
        period_label: str,
    ) -> tuple[bytes, int]:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Test yechganlar"

        span = len(SOLVER_COLUMNS)
        unique = len({attempt.user_id for attempt in attempts})

        _write_title(
            sheet,
            "Test yechganlar",
            f"Davr: {period_label}   •   "
            f"Topshiriqlar: {len(attempts)} ta   •   "
            f"Noyob o'quvchilar: {unique} ta   •   "
            f"Hisobot: {fmt_datetime(utcnow())}",
            span=span,
        )

        header_row = 4
        _write_header(sheet, SOLVER_COLUMNS, row=header_row)

        for order, attempt in enumerate(attempts, start=1):
            user = attempt.user
            test = attempt.test

            _write_row(
                sheet,
                SOLVER_COLUMNS,
                (
                    order,
                    user.full_name if user else "—",
                    user.phone if user and user.phone else "—",
                    user.telegram_id if user else "—",
                    test.number if test else "—",
                    test.title if test else "—",
                    f"{attempt.score}/{attempt.max_score}",
                    attempt.percentage / 100,
                    attempt.grade or "—",
                    "O'tdi" if attempt.is_passed else "O'tmadi",
                    (attempt.submitted_key or "").upper() or "—",
                    fmt_datetime(attempt.finished_at),
                ),
                row=header_row + order,
                fill=PASS_FILL if attempt.is_passed else FAIL_FILL,
                mono_index=11,
                percent_index=8,
            )

        if attempts:
            sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
            sheet.auto_filter.ref = (
                f"A{header_row}:{get_column_letter(span)}{header_row + len(attempts)}"
            )
        else:
            _empty_note(sheet, header_row + 1, "Bu davrda hech kim javob bermagan.")

        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()

        log.info("Excel: yechganlar=%d davr=%s", len(attempts), period_label)
        return buffer.getvalue(), len(attempts)
