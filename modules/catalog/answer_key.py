"""
Javoblar kaliti bilan ishlash.

Bu modul — tizimning eng nozik joyi. Javobni noto'g'ri o'qish darhol
noto'g'ri bahoga olib keladi, shuning uchun bu yerda hech qanday
"taxminan" ishlash yo'q: shubhali holat xato bilan tugaydi.

Bazaga ham, Telegram'ga ham bog'liq emas — sof mantiq, sinash oson.

QO'LLAB-QUVVATLANADIGAN KO'RINISHLAR
------------------------------------
Yaratish (o'qituvchi bitta xabarda):
    Matematika+abcdabcd
    Blok-3 + 1a2b3c4d

Javob berish (o'quvchi):
    abcdabcd            faqat harflar
    1a2b3c4d            raqam + harf
    12*abcdabcd         test kodi bilan
    12 abcdabcd         bo'shliq bilan (agar qolganida raqam bo'lmasa)

Qulayliklar:
    * katta/kichik harf farqi yo'q
    * bo'shliq, vergul, nuqta e'tiborsiz — ular ajratgich
    * kirill "с", "а", "в" lotinga o'giriladi (klaviatura xatosi ko'p)
    * javobsiz savol o'rniga "-" yoki "_"
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.exceptions import AnswerKeyError, ValidationError
from modules.catalog.models import ANSWER_LETTERS

#  Javobsiz savol belgisi
BLANK = "-"

#  Kalitni nomdan ajratuvchi belgi (bitta xabarda test yaratishda)
TITLE_SEPARATOR = "+"


#  Kirill va lotin harflari ko'rinishi bir xil bo'lgan juftliklar.
#  Foydalanuvchi kirill klaviaturada yozganda "с" (kirill es) lotin "c"
#  ga aynan o'xshaydi, lekin boshqa belgi — busiz javob "noto'g'ri" deb
#  o'qilardi va o'quvchi nima uchun ekanini tushunmasdi.
LOOKALIKE: dict[str, str] = {
    "а": "a", "А": "a",
    "в": "b", "В": "b",
    "с": "c", "С": "c",
    "е": "e", "Е": "e",
    "ғ": "f", "Ғ": "f",
    "н": "h", "Н": "h",
    "ԁ": "d",
}

#  Javobsiz savolni bildiruvchi belgilar.
#  ATAYLAB faqat shu ikkitasi:
#    "." — odamlar uni AJRATGICH sifatida yozadi ("a.b.c.d"), javobsiz
#          deb emas. Bo'sh javob deb olsak "a.b.c.d" -> "a-b-c-d" bo'lardi.
#    "*" — test raqamini ajratish uchun band.
#    "0" — raqam, savol tartibida uchraydi ("10a").
BLANK_CHARS: frozenset[str] = frozenset({"-", "_"})

#  "12*abcd" — aniq ajratgich (hujjatlashtirilgan format)
_CODE_EXPLICIT = re.compile(r"^\s*(\d{1,6})\s*[*x×:]\s*(.+)$", re.IGNORECASE)

#  "12 abcd" — faqat bo'shliq (noaniq, ehtiyotkorlik bilan)
_CODE_SPACE = re.compile(r"^\s*(\d{1,6})\s+(.+)$")

#  "1a2b3c" juftliklari
_NUMBERED = re.compile(r"(\d{1,3})\s*([a-h])", re.IGNORECASE)


# ======================================================================
#  NATIJA TUZILMALARI
# ======================================================================

@dataclass(slots=True, frozen=True)
class ParsedKey:
    """O'qilgan javoblar."""

    letters: str
    """Kichik harflar. Javobsiz savol o'rnida '-'."""

    test_number: int | None = None
    """'12*abcd' ko'rinishida yuborilgan bo'lsa — test raqami."""

    @property
    def length(self) -> int:
        return len(self.letters)

    @property
    def answered(self) -> int:
        """Nechta savolga javob berilgan."""
        return sum(1 for char in self.letters if char != BLANK)

    @property
    def is_empty(self) -> bool:
        return self.answered == 0


@dataclass(slots=True, frozen=True)
class OneLineTest:
    """Bitta xabardan o'qilgan test: 'Matematika+abcdabcd'."""

    title: str
    key: str
    time_limit_min: int = 0

    @property
    def questions_count(self) -> int:
        return len(self.key)


# ======================================================================
#  ICHKI YORDAMCHILAR
# ======================================================================

def _has_letter(text: str) -> bool:
    return any(char.lower() in ANSWER_LETTERS for char in text)


def _invalid_letters(text: str) -> list[str]:
    """
    Javob bo'la olmaydigan harflarni topadi (takrorsiz, tartibda).

    Raqam va tinish belgilari tekshirilmaydi — ular ajratgich bo'lishi
    mumkin. Faqat HARFLAR.
    """
    found: list[str] = []
    seen: set[str] = set()

    for char in text:
        if not char.isalpha():
            continue

        mapped = LOOKALIKE.get(char, char).lower()
        if mapped in ANSWER_LETTERS:
            continue

        if mapped not in seen:
            seen.add(mapped)
            found.append(char)

    return found


def _normalize(text: str) -> str:
    """Harflarni lotinga o'giradi, keraksiz belgilarni tashlaydi."""
    result: list[str] = []

    for char in text:
        mapped = LOOKALIKE.get(char, char).lower()

        if mapped in ANSWER_LETTERS or mapped.isdigit():
            result.append(mapped)
        elif mapped in BLANK_CHARS:
            result.append(BLANK)
        #  Qolgani (bo'shliq, vergul, nuqta, yangi qator) tashlanadi

    return "".join(result)


def _extract(normalized: str) -> str:
    """
    Normallashtirilgan matndan javob harflarini ajratadi.

    Ikki ko'rinish farqlanadi:
        "1a2b3c"  — raqamlar savol tartibi, harflar javob
        "abc"     — faqat javoblar

    Raqamli ko'rinishda tartib HISOBGA OLINADI: "3c1a2b" -> "abc".
    """
    if not any(char.isdigit() for char in normalized):
        return "".join(
            char for char in normalized
            if char in ANSWER_LETTERS or char == BLANK
        )

    pairs = _NUMBERED.findall(normalized)
    if not pairs:
        #  Raqamlar bor, lekin juftlik yo'q — raqamlarni tashlaymiz
        return "".join(
            char for char in normalized
            if char in ANSWER_LETTERS or char == BLANK
        )

    numbered: dict[int, str] = {}
    for number_text, letter in pairs:
        try:
            position = int(number_text)
        except ValueError:
            continue
        if position >= 1:
            #  Takror kelsa oxirgisi kuchda qoladi
            numbered[position] = letter.lower()

    if not numbered:
        return ""

    highest = max(numbered)
    return "".join(numbered.get(index, BLANK) for index in range(1, highest + 1))


# ======================================================================
#  TEST RAQAMINI AJRATISH
# ======================================================================

def split_test_number(raw: str) -> tuple[int | None, str]:
    """
    '12*abcd' dan test raqamini ajratadi.

    NOZIK JOY — NOANIQLIK
    ---------------------
    Bo'shliqni ajratgich deb qabul qilish xavfli:

        "2 b 1 a"  ->  "2-test, javob 'b 1 a'" MI,
                       yoki "2-savol=b, 1-savol=a" MI?

    Qoida:
        * Aniq ajratgich (`*`, `:`, `x`) — doim test raqami.
          Bot ko'rsatmasida aynan shu format yozilgan.
        * Faqat bo'shliq — qolgan qismda RAQAM BO'LMASAGINA:
              "12 abcdabcd"  ->  12-test                    ✅
              "2 b 1 a"      ->  savol tartibi, test emas   ✅

    Returns:
        (test_raqami yoki None, qolgan matn)
    """
    match = _CODE_EXPLICIT.match(raw)
    if match and _has_letter(match.group(2)):
        try:
            return int(match.group(1)), match.group(2)
        except ValueError:
            return None, raw

    match = _CODE_SPACE.match(raw)
    if match:
        rest = match.group(2)
        if _has_letter(rest) and not any(char.isdigit() for char in rest):
            try:
                return int(match.group(1)), rest
            except ValueError:
                return None, raw

    return None, raw


# ======================================================================
#  JAVOBLARNI O'QISH
# ======================================================================

def parse_answers(raw: str, *, expected: int | None = None) -> ParsedKey:
    """
    O'quvchi yuborgan matndan javoblarni o'qiydi.

    Args:
        raw: xom matn
        expected: kutilayotgan savollar soni (None — tekshirilmaydi)

    Raises:
        AnswerKeyError: o'qib bo'lmadi yoki uzunlik mos kelmadi
    """
    if not raw or not raw.strip():
        raise AnswerKeyError("Javoblar yuborilmadi.")

    test_number, body = split_test_number(raw)

    #  Ruxsatsiz harfni ALOHIDA ushlaymiz. Busiz u jimgina tashlanardi
    #  va foydalanuvchi "10 ta kerak, 9 ta yuborildi" degan chalkash
    #  xatoni ko'rardi — aslida muammo sonda emas, harfda.
    invalid = _invalid_letters(body)
    if invalid:
        shown = ", ".join(f"<code>{char}</code>" for char in invalid)
        raise AnswerKeyError(
            f"Javob bo'la olmaydigan harf ishlatilgan: {shown}",
            hint=(
                f"Faqat <b>{ANSWER_LETTERS.upper()}</b> harflaridan foydalaning.\n"
                f"Javobsiz savol o'rniga <code>-</code> qo'ying."
            ),
        )

    letters = _extract(_normalize(body))

    if not letters:
        raise AnswerKeyError(
            "Javoblarni o'qiy olmadim.",
            hint=(
                "To'g'ri ko'rinishlar:\n"
                "  <code>abcdabcd</code>\n"
                "  <code>1a2b3c4d</code>\n"
                "  <code>12*abcdabcd</code>"
            ),
        )

    if expected is not None and len(letters) != expected:
        raise AnswerKeyError(
            "Javoblar soni mos kelmadi.",
            hint=(
                f"Kerak: <b>{expected} ta</b>\n"
                f"Yuborildi: <b>{len(letters)} ta</b>\n\n"
                f"Javobsiz savol o'rniga <code>-</code> qo'ying."
            ),
        )

    return ParsedKey(letters=letters, test_number=test_number)


def parse_author_key(raw: str, *, expected: int | None = None) -> str:
    """
    O'QITUVCHI kiritgan to'g'ri javoblar kalitini o'qiydi.

    O'quvchinikidan farqi: bo'sh javob BO'LISHI MUMKIN EMAS — har bir
    savolning to'g'ri javobi ma'lum bo'lishi shart.

    Returns:
        Tozalangan kalit (kichik harflar).
    """
    parsed = parse_answers(raw, expected=expected)

    if BLANK in parsed.letters:
        blanks = [
            str(index + 1)
            for index, char in enumerate(parsed.letters)
            if char == BLANK
        ]
        raise AnswerKeyError(
            "Kalitda javobsiz savol bo'lishi mumkin emas.",
            hint=f"Javob ko'rsatilmagan: <b>{', '.join(blanks)}-savol</b>",
        )

    return parsed.letters


# ======================================================================
#  BITTA XABARDA TEST YARATISH
# ======================================================================

_ONE_LINE_TIMER = re.compile(r"\s+(?:t|timer|vaqt):?\s*(\d{1,3})\s*$", re.IGNORECASE)


def parse_one_line(raw: str, *, max_questions: int = 200) -> OneLineTest:
    """
    'Matematika+abcdabcd' ko'rinishidagi xabardan test yasaydi.

    Bu — eng tez yaratish usuli. Nom va kalit `+` bilan ajratiladi.
    Ixtiyoriy ravishda oxirida `t:30` (30 daqiqa taymer) yozish mumkin.

    Raises:
        ValidationError: format noto'g'ri
        AnswerKeyError: kalitni o'qib bo'lmadi
    """
    if TITLE_SEPARATOR not in raw:
        raise ValidationError(
            "Format noto'g'ri.",
            hint=(
                "Test nomi va kalitni <code>+</code> bilan ajrating:\n\n"
                "<code>Matematika+abcdabcd</code>\n"
                "<code>Blok-3+1a2b3c4d t:30</code>"
            ),
        )

    #  Oxirgi `+` bo'yicha ajratamiz — nomda ham `+` bo'lishi mumkin
    #  ("A+ daraja+abcd" kabi holat ishlashi kerak)
    title_part, _, key_part = raw.rpartition(TITLE_SEPARATOR)

    title = title_part.strip()
    if len(title) < 2:
        raise ValidationError(
            "Test nomi juda qisqa.",
            hint="Kamida 2 ta belgi kiriting: <code>Matematika+abcdabcd</code>",
        )
    if len(title) > 160:
        raise ValidationError("Test nomi juda uzun (ko'pi bilan 160 ta belgi).")

    time_limit_min = 0
    timer_match = _ONE_LINE_TIMER.search(key_part)
    if timer_match:
        time_limit_min = int(timer_match.group(1))
        key_part = key_part[:timer_match.start()].strip()

    key = parse_author_key(key_part)

    if len(key) > max_questions:
        raise ValidationError(
            f"Ko'pi bilan {max_questions} ta savol bo'lishi mumkin.",
            hint=f"Siz {len(key)} ta javob yubordingiz.",
        )

    return OneLineTest(title=title, key=key, time_limit_min=time_limit_min)


# ======================================================================
#  SOLISHTIRISH
# ======================================================================

def compare(correct: str, submitted: str) -> list[bool | None]:
    """
    Javoblarni to'g'ri kalit bilan solishtiradi.

    Returns:
        Har savol uchun: True (to'g'ri) / False (xato) / None (javobsiz)
    """
    result: list[bool | None] = []

    for index, expected in enumerate(correct.lower()):
        given = submitted[index].lower() if index < len(submitted) else BLANK
        result.append(None if given == BLANK else given == expected)

    return result


def count_differences(old: str, new: str) -> int:
    """Ikki kalit nechta savolda farq qiladi."""
    return sum(
        1 for index in range(max(len(old), len(new)))
        if (old[index] if index < len(old) else None)
        != (new[index] if index < len(new) else None)
    )


def diff_positions(old: str, new: str) -> list[tuple[int, str, str]]:
    """
    Farq qilgan savollar ro'yxati.

    Returns:
        [(savol_raqami, eski_harf, yangi_harf), ...]
    """
    changes: list[tuple[int, str, str]] = []

    for index in range(max(len(old), len(new))):
        before = old[index].upper() if index < len(old) else "—"
        after = new[index].upper() if index < len(new) else "—"
        if before != after:
            changes.append((index + 1, before, after))

    return changes


def format_key(key: str, *, per_line: int = 10) -> str:
    """
    Kalitni o'qishga qulay ko'rinishda chiqaradi:

        1-10:   A B C D A B C D A B
        11-20:  C D A B C D A B C D
    """
    key = key.lower()
    if not key:
        return "—"

    lines: list[str] = []
    for start in range(0, len(key), per_line):
        chunk = key[start : start + per_line]
        label = f"{start + 1}-{start + len(chunk)}"
        letters = " ".join(char.upper() for char in chunk)
        lines.append(f"<code>{label:>7}:</code>  {letters}")

    return "\n".join(lines)
