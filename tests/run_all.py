#!/usr/bin/env python3
"""
TestLab — Barcha sinovlarni ketma-ket yurgizuvchi yagona skript.

Ishga tushirish:
    python tests/run_all.py
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    test_files = sorted(glob.glob("tests/test_*.py"))
    if not test_files:
        print("❌ Hech qanday test fayli topilmadi!")
        return 1

    print("==================================================")
    print(f"🚀 TestLab — Barcha {len(test_files)} ta testlarni ishga tushirish")
    print("==================================================")

    passed = 0
    failed = 0
    failures: list[tuple[str, str, str]] = []
    total_start = time.monotonic()

    for idx, test_file in enumerate(test_files, start=1):
        name = os.path.basename(test_file)
        print(f"[{idx:02d}/{len(test_files):02d}] {name:<35} ... ", end="", flush=True)

        t0 = time.monotonic()
        res = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        duration = time.monotonic() - t0

        if res.returncode == 0:
            passed += 1
            print(f"✅ PASS ({duration:.2f}s)")
        else:
            failed += 1
            print(f"❌ FAIL (exit {res.returncode}, {duration:.2f}s)")
            failures.append((name, res.stdout, res.stderr))

    total_duration = time.monotonic() - total_start
    print("==================================================")
    print(f"🏁 Yakunlandi: {passed}/{len(test_files)} ta muvaffaqiyatli, {failed} ta xato.")
    print(f"⏱ Jami ketgan vaqt: {total_duration:.1f} soniya.")
    print("==================================================")

    if failures:
        print("\n❌ XATOLIKLAR RO'YXATI:")
        for name, stdout, stderr in failures:
            print(f"\n--- {name} ---")
            if stdout:
                print("STDOUT:\n" + stdout[-1000:])
            if stderr:
                print("STDERR:\n" + stderr[-1000:])
        return 1

    print("\n🎉 BARCHA SINOVLAR 100% MUVAFFAQIYATLI O'TDI! Serverga yuklashga tayyor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
