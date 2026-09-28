@echo off
chcp 65001 >nul
echo ========================================================
echo   TestLab jarayonlarini to'xtatish...
echo ========================================================

taskkill /F /IM cloudflared-windows-amd64.exe >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1
echo Cloudflare tunnel to'xtatildi.

echo.
echo Agar bot alohida terminal oynasida ochiq bo'lsa, o'sha oynada Ctrl+C bosing.
pause
