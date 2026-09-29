#!/usr/bin/env bash
# ==========================================================
#  TestLab — Linux (Ubuntu / Debian) 1-Click Server Setup
# ==========================================================

set -euo pipefail

echo "=========================================="
echo "🚀 TestLab Server O'rnatish Skripti"
echo "=========================================="

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "📂 Loyiha papkasi: $APP_DIR"

# 1. Tizim paketlarini yangilash va kerakli paketlarni o'rnatish
echo "📦 Tizim paketlari tekshirilmoqda..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv libpq-dev build-essential libjpeg-dev zlib1g-dev

# 2. Virtual muhit (venv) yaratish
if [ ! -d "venv" ]; then
    echo "🐍 Virtual muhit yaratilmoqda (venv)..."
    python3 -m venv venv
fi

# 3. Bog'liqliklarni o'rnatish
echo "📥 Python paketlari o'rnatilmoqda..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 4. Kerakli papkalarni yaratish
echo "📁 data, logs, exports, assets papkalari tayyorlanmoqda..."
mkdir -p data logs exports assets/fonts assets/generated

# 5. .env fayli mavjudligini tekshirish
if [ ! -f ".env" ]; then
    echo "⚠️ .env fayli topilmadi. .env.example dan nusxalanmoqda..."
    cp .env.example .env
    echo "❗ ILTIMOS: .env faylini ochib, BOT_TOKEN va ADMIN_IDS ni to'ldiring:"
    echo "   nano $APP_DIR/.env"
fi

# 6. Systemd xizmatini o'rnatish
SERVICE_SRC="$APP_DIR/deploy/testlab.service"
SERVICE_DEST="/etc/systemd/system/testlab.service"

if [ -f "$SERVICE_SRC" ]; then
    echo "⚙️  Systemd xizmati sozlanmoqda..."
    # Foydalanuvchi va katalog yo'llarini joriy tizimga moslash
    CURRENT_USER="$(whoami)"
    sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$APP_DIR|g" "$SERVICE_SRC"
    sudo sed -i "s|ExecStart=.*|ExecStart=$APP_DIR/venv/bin/python run.py|g" "$SERVICE_SRC"
    sudo sed -i "s|EnvironmentFile=.*|EnvironmentFile=$APP_DIR/.env|g" "$SERVICE_SRC"
    sudo sed -i "s|StandardOutput=.*|StandardOutput=append:$APP_DIR/logs/systemd.log|g" "$SERVICE_SRC"
    sudo sed -i "s|StandardError=.*|StandardError=append:$APP_DIR/logs/systemd_err.log|g" "$SERVICE_SRC"
    sudo sed -i "s|User=.*|User=$CURRENT_USER|g" "$SERVICE_SRC"

    sudo cp "$SERVICE_SRC" "$SERVICE_DEST"
    sudo systemctl daemon-reload
    sudo systemctl enable testlab.service
    echo "✅ Xizmat yoqildi: systemctl start testlab"
fi

echo "=========================================="
echo "🎉 O'rnatish muvaffaqiyatli yakunlandi!"
echo ""
echo "Botni ishga tushirish uchun:"
echo "   sudo systemctl start testlab"
echo ""
echo "Holatini tekshirish:"
echo "   sudo systemctl status testlab"
echo ""
echo "Loglarni jonli ko'rish:"
echo "   sudo journalctl -u testlab -f"
echo "=========================================="
