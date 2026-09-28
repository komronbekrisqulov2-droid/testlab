@echo off
chcp 65001 >nul
title TestLab Bot
echo ========================================================
echo   TestLab Telegram Bot ishga tushirilmoqda...
echo ========================================================

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe run.py
) else (
    python run.py
)
pause
