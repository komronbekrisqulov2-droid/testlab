"""
Sinovlar uchun ALOHIDA baza.

⚠️ NIMA UCHUN BU FAYL BOR
--------------------------
Sinovlar `drop_all()` + `create_all()` qiladi — ya'ni jadvallarni
o'chirib, qaytadan yaratadi. Agar ular `.env` dagi bazani ishlatsa,
**ishlaydigan botning ma'lumotlari yo'q qilinadi**.

Aynan shu bo'lgan edi: sinovlar ishlaydigan bazani tozalab yubordi.

Shuning uchun har bir sinov fayli boshqa importlardan OLDIN shuni
chaqiradi:

    from tests import _env  # noqa: F401

`core.config` va `infrastructure.database.engine` import paytida
`DATABASE_URL` ni o'qiydi — demak o'zgaruvchi ULARDAN OLDIN
o'rnatilishi shart. Import tartibi bu yerda muhim.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#  Windows konsoli standart holda cp1252 — sinov nomlaridagi emoji
#  `UnicodeEncodeError` bilan butun jarayonni yiqitadi. Sinov qaysi
#  terminalda ishga tushirilishidan qat'i nazar ishlashi kerak.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

#  Sinov bazasi — loyihaning `data/` katalogidan TASHQARIDA
TEST_DB_PATH: Path = Path(__file__).resolve().parent / "_test.db"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

#  Sinovlar bot tokenisiz ham ishlashi kerak
os.environ.setdefault("BOT_TOKEN", "123456789:AAFakeTokenForTests1234567890abcd")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("LOG_LEVEL", "WARNING")


def reset() -> None:
    """Oldingi seansdan qolgan sinov bazasini o'chiradi."""
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(str(TEST_DB_PATH) + suffix)
        if candidate.exists():
            try:
                candidate.unlink()
            except OSError:
                pass


reset()
