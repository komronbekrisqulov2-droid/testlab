"""
Natija matni sinovi.

⚠️ NIMA UCHUN BU SINOV BOR
--------------------------
Telegram xabari **4096 belgi** bilan cheklangan. Har bir savol qatori
~30 belgi, ya'ni 150 savolli testda natija xabari chegaradan oshib
ketardi va **umuman yuborilmasdi** — o'quvchi natijasini ko'rmasdi.

`MAX_QUESTIONS=200` bo'lgani uchun bu nazariy emas, real xato edi.

Ishga tushirish:
    python tests/test_result_text.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests import _env  # noqa: F401,E402

from apps.bot.texts import uz  # noqa: E402
from apps.bot.utils import MAX_MESSAGE_LENGTH  # noqa: E402
from modules.assessment.service import QuestionResult  # noqa: E402

_failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}\n         kutilgan: {want!r}\n         olingan : {got!r}")
        _failures.append(label)


def check_true(label: str, value: bool) -> None:
    check(label, bool(value), True)


@dataclass
class FakeTest:
    number: int = 12
    title: str = "Blok-3 Matematika"
    questions_count: int = 0
    author_name: str = "Saxobiddin Karimov"


@dataclass
class FakeSubmit:
    test: object
    questions: list
    correct: int
    wrong: int
    skipped: int
    percentage: float
    grade: str
    rank: int
    participants: int
    xp_earned: int
    streak: int = 0
    streak_grew: bool = False


def make(count: int, *, wrong_every: int = 4, skipped: int = 0) -> FakeSubmit:
    """
    Soxta natija yasaydi.

    `wrong_every` — har nechanchi savol xato bo'lsin (0 = hammasi to'g'ri)
    """
    questions: list[QuestionResult] = []
    correct = wrong = skip = 0

    for index in range(count):
        if skip < skipped:
            verdict, given = None, None
            skip += 1
        elif wrong_every and index % wrong_every == 0:
            verdict, given = False, "A"
            wrong += 1
        else:
            verdict, given = True, "C"
            correct += 1

        questions.append(
            QuestionResult(number=index + 1, given=given, correct="C", verdict=verdict)
        )

    percentage = round(correct / count * 100, 1) if count else 0.0

    return FakeSubmit(
        test=FakeTest(questions_count=count),
        questions=questions,
        correct=correct,
        wrong=wrong,
        skipped=skip,
        percentage=percentage,
        grade="B",
        rank=3,
        participants=42,
        xp_earned=55,
    )


# ======================================================================

def test_length_limit() -> None:
    """Hech qanday savol sonida chegaradan oshmasligi kerak."""
    print("\n--- Telegram chegarasi (4096 belgi) ---")

    for count in (5, 10, 25, 30, 50, 100, 150, 200):
        text = uz.result(make(count))
        fits = len(text) <= MAX_MESSAGE_LENGTH
        status = f"{len(text):>5} belgi"
        check(f"{count:>3} savol -> {status}", fits, True)


def test_worst_case() -> None:
    """Eng yomon holat: 200 savol, HAMMASI xato."""
    print("\n--- Eng yomon holat ---")

    text = uz.result(make(200, wrong_every=1))
    check_true(f"200 ta xato -> {len(text)} belgi", len(text) <= MAX_MESSAGE_LENGTH)

    text = uz.result(make(200, wrong_every=1, skipped=200))
    check_true(f"200 ta javobsiz -> {len(text)} belgi", len(text) <= MAX_MESSAGE_LENGTH)


def test_full_mode() -> None:
    """25 tagacha — barcha savollar ko'rsatiladi."""
    print("\n--- To'liq ko'rinish (<= 25 savol) ---")

    text = uz.result(make(10))
    check_true("har bir savol qatori bor", text.count("ball") == 10)
    check_true("to'g'ri belgisi", "✅" in text)
    check_true("xato belgisi", "❌" in text)
    check_true("xulosa bor", "Jami:" in text)


def test_compact_mode() -> None:
    """25 dan ko'p — faqat xatolar."""
    print("\n--- Qisqa ko'rinish (> 25 savol) ---")

    submit = make(100)
    text = uz.result(submit)

    check_true("«Xatolar» sarlavhasi", "Xatolar" in text)
    check_true("to'g'ri qatorlar yo'q", "1 ball" not in text)
    check_true("to'g'rilar soni aytiladi", f"{submit.correct} ta savol to'g'ri" in text)
    check_true("xulosa saqlangan", "Jami:" in text)
    check_true("baho saqlangan", "Baho:" in text)
    check_true("reyting saqlangan", "o'rin" in text)

    #  Har bir xato ko'rsatilgan bo'lishi kerak (chegaradan kam bo'lsa)
    check("xatolar soni matnda", text.count("to'g'risi:"), submit.wrong)


def test_mistake_cap() -> None:
    """Juda ko'p xato bo'lsa ro'yxat kesiladi."""
    print("\n--- Xatolar chegarasi ---")

    submit = make(200, wrong_every=1)
    text = uz.result(submit)

    check("ko'rsatilgan xatolar", text.count("to'g'risi:"), uz.MAX_MISTAKES_SHOWN)
    check_true("qolgani aytiladi", "va yana" in text)
    check_true("chegaraga sig'di", len(text) <= MAX_MESSAGE_LENGTH)


def test_perfect_compact() -> None:
    """Katta testda bitta ham xato yo'q."""
    print("\n--- Xatosiz (katta test) ---")

    text = uz.result(make(50, wrong_every=0))
    check_true("tabrik matni", "Bitta ham xato yo'q" in text)
    check_true("chegaraga sig'di", len(text) <= MAX_MESSAGE_LENGTH)


def test_skipped_shown() -> None:
    """Javobsiz savollar ham xatolar ro'yxatiga tushadi."""
    print("\n--- Javobsizlar ---")

    submit = make(40, wrong_every=0, skipped=5)
    text = uz.result(submit)
    check_true("javobsizlar ko'rsatilgan", "➖" in text)
    check("javobsizlar soni", text.count("to'g'risi:"), 5)


def test_streak_line() -> None:
    """Seriya qatori faqat u O'SGAN kunda chiqadi."""
    print("\n--- Seriya qatori ---")

    quiet = make(10)
    check_true("seriyasiz natijada yo'q", "ketma-ket" not in uz.result(quiet))

    #  Birinchi kun: seriya bor, lekin bu hali «seriya» emas
    first_day = make(10)
    first_day.streak, first_day.streak_grew = 1, True
    check_true("birinchi kunda ko'rsatilmaydi", "ketma-ket" not in uz.result(first_day))

    grown = make(10)
    grown.streak, grown.streak_grew = 5, True
    check_true("o'sgan kunda ko'rsatiladi", "5 kun ketma-ket" in uz.result(grown))

    #  O'sha kunning ikkinchi testi — takrorlanib e'tibordan qolmasin
    same_day = make(10)
    same_day.streak, same_day.streak_grew = 5, False
    check_true("takroriy testda ko'rsatilmaydi", "ketma-ket" not in uz.result(same_day))


# ======================================================================

def main() -> int:
    print("\n  TestLab — natija matni sinovlari")

    test_length_limit()
    test_worst_case()
    test_full_mode()
    test_compact_mode()
    test_mistake_cap()
    test_perfect_compact()
    test_skipped_shown()
    test_streak_line()

    print()
    if _failures:
        print(f"  {len(_failures)} ta sinov muvaffaqiyatsiz:")
        for name in _failures:
            print(f"    - {name}")
        return 1

    print("  NATIJA MATNI TO'G'RI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
