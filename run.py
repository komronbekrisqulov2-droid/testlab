#!/usr/bin/env python3
"""
TestLab — ishga tushirish skripti.

    python run.py

Loyihani qaysi katalogdan ishga tushirishdan qat'i nazar import
yo'llari to'g'ri ishlashi uchun loyiha ildizi `sys.path` ga qo'shiladi.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.bot.main import main  # noqa: E402

if __name__ == "__main__":
    main()
