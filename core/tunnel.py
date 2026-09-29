"""
Cloudflare Tunnel boshqaruv moduli.

pycloudflared kutubxonasida Windows'da stderr quvuri o'qilmay qolib,
OS buferi to'lgach cloudflared jarayoni bloklanib qolishi (Error 1033)
va bot qayta ishga tushganda eski jarayonlar o'lmay qolishi muammosi bor.
Ushbu modul alohida fonda stderr oqimini doimiy o'qib bo'shatib turadi
va tunnelni 100% barqaror ushlaydi.
"""

from __future__ import annotations

import atexit
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import NamedTuple

from core.logging import get_logger

log = get_logger(__name__)

URL_PATTERN = re.compile(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)")


class TunnelInfo(NamedTuple):
    url: str
    process: subprocess.Popen


_active_tunnel: TunnelInfo | None = None


def get_cloudflared_path() -> Path | None:
    base = (
        Path(sys.prefix)
        / "Lib"
        / "site-packages"
        / "pycloudflared"
        / "cloudflared-windows-amd64.exe"
    )
    if base.exists():
        return base
    try:
        from pycloudflared.util import get_info
        exe_path = Path(get_info().executable)
        if exe_path.exists():
            return exe_path
    except Exception:
        pass
    which_path = shutil.which("cloudflared")
    if which_path:
        return Path(which_path)
    return None


def kill_orphan_cloudflared() -> None:
    """Eski qolib ketgan cloudflared jarayonlarini tozalaydi."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/IM", "cloudflared-windows-amd64.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "cloudflared.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            subprocess.run(
                ["pkill", "-f", "cloudflared"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    except Exception as e:
        log.debug("Eski cloudflared tozalashda xato: %s", e)


def start_cloudflare_tunnel(port: int, wait_timeout: float = 15.0) -> str | None:
    """
    Cloudflare tunnelni ishga tushiradi va HTTPS havolani qaytaradi.
    Stderr quvuri doimiy o'qib turiladi, shuning uchun Windows OS da qotib qolmaydi.
    """
    global _active_tunnel
    exe = get_cloudflared_path()
    if exe is None or not exe.exists():
        log.warning("cloudflared topilmadi: %s", exe)
        return None

    kill_orphan_cloudflared()

    cmd = [
        str(exe),
        "tunnel",
        "--url",
        f"http://127.0.0.1:{port}",
        "--no-autoupdate",
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:
        log.error("cloudflared ishga tushirishda xato: %s", exc)
        return None

    found_url: list[str] = []
    url_event = threading.Event()

    def _drain_stderr():
        assert process.stderr is not None
        while process.poll() is None:
            line = process.stderr.readline()
            if not line:
                break
            if not url_event.is_set():
                match = URL_PATTERN.search(line)
                if match:
                    found_url.append(match.group(1))
                    url_event.set()

    drain_thread = threading.Thread(target=_drain_stderr, daemon=True)
    drain_thread.start()

    url_event.wait(timeout=wait_timeout)

    if not found_url:
        log.warning("Cloudflare tunnel URL topilmadi")
        return None

    tunnel_url = found_url[0]
    _active_tunnel = TunnelInfo(url=tunnel_url, process=process)
    atexit.register(stop_cloudflare_tunnel)
    return tunnel_url


def stop_cloudflare_tunnel() -> None:
    """Tunnel jarayonini xavfsiz to'xtatadi."""
    global _active_tunnel
    if _active_tunnel and _active_tunnel.process:
        try:
            _active_tunnel.process.terminate()
            _active_tunnel.process.wait(timeout=3)
        except Exception:
            try:
                _active_tunnel.process.kill()
            except Exception:
                pass
        _active_tunnel = None
    kill_orphan_cloudflared()
