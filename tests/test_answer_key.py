"""
Javob kaliti sinovlari.

Ishga tushirish:
    python tests/test_answer_key.py

Nega aynan shu modul batafsil sinaladi? Chunki javobni noto'g'ri o'qish
darhol noto'g'ri bahoga olib keladi — o'quvchi haqsiz yiqiladi va buni
isbotlash qiyin. Bazaga bog'liq emas, shuning uchun sinov tez.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#  ⚠️ MUHIM: engine importidan OLDIN — sinov ALOHIDA bazani ishlatadi,
#  aks holda ishlaydigan botning ma'lumotlari o'chib ketadi.
from tests import _env  # noqa: F401,E402

from core.exceptions import AnswerKeyError, ValidationError  # noqa: E402
from modules.catalog.answer_key import (  # noqa: E402
    compare,
    format_key,
    parse_answers,
    parse_author_key,
    parse_one_line,
    split_test_number,
)

#  Haqiqiy 25 savolli kalit (raqamli formatda yozilgan)
REAL_RAW = "1c2b3c4d5c6c7d8c9d10d11c12b13a14a15a16c17b18c19d20c21d22c23a24a25b"
REAL_KEY = "cbcdccdcddcbaaacbcdcdcaab"

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


def expect_error(label: str, func, *args, error=AnswerKeyError, **kwargs) -> None:
    """Funksiya xato berishi kerakligini tekshiradi."""
    try:
        func(*args, **kwargs)
    except error:
        print(f"  OK   {label}")
    except Exception as unexpected:
        print(f"  FAIL {label}\n         kutilgan xato: {error.__name__}"
              f"\n         olingan       : {type(unexpected).__name__}")
        _failures.append(label)
    else:
        print(f"  FAIL {label} — xato kutilgan edi, lekin o'tib ketdi")
        _failures.append(label)


# ======================================================================

def test_reading() -> None:
    print("\n--- Javoblarni o'qish ---")
    check("raqamli format", parse_answers(REAL_RAW).letters, REAL_KEY)
    check("uzunlik 25", parse_answers(REAL_RAW).length, 25)
    check("faqat harflar", parse_answers("abcdabcd").letters, "abcdabcd")
    check("katta harf", parse_answers("ABCD").letters, "abcd")
    check("bo'shliqlar", parse_answers("a b c d").letters, "abcd")
    check("vergul", parse_answers("a, b, c, d").letters, "abcd")
    check("nuqta ajratgich", parse_answers("a.b.c.d").letters, "abcd")
    check("yangi qator", parse_answers("ab\ncd").letters, "abcd")
    check("A dan H gacha", parse_answers("abcdefgh").letters, "abcdefgh")


def test_cyrillic() -> None:
    print("\n--- Kirill klaviatura ---")
    check("kirill s,a,v -> c,a,b", parse_answers("сав").letters, "cab")
    check("aralash", parse_answers("aсb").letters, "acb")


def test_blanks() -> None:
    print("\n--- Javobsiz savollar ---")
    parsed = parse_answers("ab-d")
    check("bo'sh saqlandi", parsed.letters, "ab-d")
    check("javob berilgan soni", parsed.answered, 3)
    check("bo'sh emas", parsed.is_empty, False)
    check("pastki chiziq ham", parse_answers("ab_d").letters, "ab-d")


def test_ordering() -> None:
    print("\n--- Savol tartibi ---")
    check("3c1a2b -> abc", parse_answers("3c1a2b").letters, "abc")
    check("tushib qolgan bo'sh", parse_answers("1a3c").letters, "a-c")
    check("takror -> oxirgisi", parse_answers("1a1c").letters, "c")
    check("10 dan katta", parse_answers("1a10b").letters, "a--------b")


def test_test_number() -> None:
    print("\n--- Test raqamini ajratish ---")
    check("12*abcd", split_test_number("12*abcd")[0], 12)
    check("12:abcd", split_test_number("12:abcd")[0], 12)
    check("12 x abcd", split_test_number("12 x abcd")[0], 12)
    check("12 abcd (bo'shliq)", split_test_number("12 abcd")[0], 12)
    check("kalit bilan", parse_answers("12*" + REAL_RAW).test_number, 12)
    check("kalit saqlandi", parse_answers("12*" + REAL_RAW).letters, REAL_KEY)

    #  Noaniqlik: raqamlar savol tartibi, test kodi EMAS
    check("'2 b 1 a' test emas", split_test_number("2 b 1 a")[0], None)
    check("'2 b 1 a' -> ab", parse_answers("2 b 1 a").letters, "ab")
    check("'1a2b' test emas", parse_answers("1a2b").test_number, None)


def test_errors() -> None:
    print("\n--- Xatolar ---")
    for bad in ("", "   ", "!!!", "123456"):
        expect_error(f"{bad!r} rad etiladi", parse_answers, bad)

    expect_error("noto'g'ri harf 'x'", parse_answers, "abcdxbcd")
    expect_error("uzunlik nomuvofiqligi", parse_answers, "abc", expected=5)
    expect_error("tasodifiy matn", parse_answers, "salom dunyo", expected=25)

    #  Xato matnida aynan qaysi harf noto'g'ri ekani ko'rsatilishi kerak
    try:
        parse_answers("abcdxbcd")
    except AnswerKeyError as error:
        text = error.user_text()
        check("xato harfni nomlaydi", "x" in text, True)
        check("ruxsat etilganini aytadi", "ABCDEFGH" in text, True)


def test_author_key() -> None:
    print("\n--- O'qituvchi kaliti ---")
    check("to'liq kalit", parse_author_key(REAL_RAW, expected=25), REAL_KEY)
    expect_error("bo'sh javob taqiqlangan", parse_author_key, "ab-d")

    try:
        parse_author_key("ab-d")
    except AnswerKeyError as error:
        check("qaysi savol bo'shligini aytadi", "3-savol" in error.user_text(), True)


def test_one_line() -> None:
    print("\n--- Bitta xabarda test yaratish ---")
    result = parse_one_line("Matematika+abcdabcd")
    check("nom", result.title, "Matematika")
    check("kalit", result.key, "abcdabcd")
    check("savollar soni", result.questions_count, 8)

    check("bo'shliqlar tozalanadi",
          parse_one_line("  Blok-3  +  abcd  ").title, "Blok-3")
    check("raqamli kalit",
          parse_one_line("Fizika+1a2b3c").key, "abc")
    check("nomdagi + saqlanadi",
          parse_one_line("A+ daraja+abcd").title, "A+ daraja")
    check("uzun nom",
          parse_one_line("Blok-3 · Matematika (2-variant)+abcd").title,
          "Blok-3 · Matematika (2-variant)")

    expect_error("ajratgichsiz", parse_one_line, "Matematika abcd", error=ValidationError)
    expect_error("nomsiz", parse_one_line, "+abcd", error=ValidationError)
    expect_error("qisqa nom", parse_one_line, "A+abcd", error=ValidationError)
    expect_error("kalitsiz", parse_one_line, "Matematika+")
    expect_error("bo'sh javobli kalit", parse_one_line, "Matematika+ab-d")
    expect_error("chegaradan oshiq", parse_one_line, "Test+" + "a" * 250,
                 error=ValidationError, max_questions=200)


def test_compare() -> None:
    print("\n--- Solishtirish ---")
    submitted = list(REAL_KEY)
    submitted[4] = "a"   # 5-savol xato
    submitted[6] = "c"   # 7-savol xato
    verdicts = compare(REAL_KEY, "".join(submitted))

    check("jami 25", len(verdicts), 25)
    check("5-savol xato", verdicts[4], False)
    check("7-savol xato", verdicts[6], False)
    check("to'g'rilar 23", sum(1 for v in verdicts if v is True), 23)
    check("javobsiz yo'q", sum(1 for v in verdicts if v is None), 0)

    check("bo'sh -> None", compare("abc", "a-c")[1], None)
    check("qisqa javob", len(compare("abcde", "ab")), 5)
    check("qisqasi javobsiz", compare("abcde", "ab")[3], None)
    check("registr farqi yo'q", compare("abc", "ABC"), [True, True, True])


def test_format() -> None:
    print("\n--- Kalit ko'rinishi ---")
    preview = format_key("abcdabcdabcd")
    check("birinchi qator", "1-10" in preview, True)
    check("ikkinchi qator", "11-12" in preview, True)
    check("bo'sh kalit", format_key(""), "—")


# ======================================================================

def main() -> int:
    print("\n  TestLab — javob kaliti sinovlari")

    test_reading()
    test_cyrillic()
    test_blanks()
    test_ordering()
    test_test_number()
    test_errors()
    test_author_key()
    test_one_line()
    test_compare()
    test_format()

    print()
    if _failures:
        print(f"  {len(_failures)} ta sinov muvaffaqiyatsiz:")
        for name in _failures:
            print(f"    - {name}")
        return 1

    print("  BARCHA SINOVLAR O'TDI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
