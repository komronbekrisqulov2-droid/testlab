# 🚀 TestLab — Serverga Joylashtirish (Production Deployment Guide)

Ushbu qo'llanma **TestLab** botini va uning Telegram Mini App (Web App) serverini Linux serverga (Ubuntu 22.04 / 24.04 LTS tavsiya etiladi) 100% xatosiz va barqaror o'rnatish uchun mo'ljallangan.

---

## 1. Tayyorgarlik va Serverga Yuklash

Serverga SSH orqali kiring va loyihani yuklang:

```bash
# Serverdagi loyiha papkasiga o'ting
cd /var/www  # yoki /home/ubuntu
git clone <sizning_repository_havolangiz> testlab
cd testlab
```

---

## 2. 1-Klik Avtomatlashtirilgan O'rnatish (Tavsiya etiladi)

Loyiha ichidagi `deploy/setup.sh` skriptini ishga tushiring:

```bash
chmod +x deploy/setup.sh
./deploy/setup.sh
```

Ushbu skript:
1. Tizim paketlarini (Python 3.11/3.12, venv, libpq-dev, Pillow build vositalari) o'rnatadi.
2. `venv` virtual muhitini yaratadi va barcha `requirements.txt` bog'liqliklarini o'rnatadi.
3. Kerakli papkalarni (`data`, `logs`, `exports`, `assets`) ochadi.
4. `.env` faylini yaratadi va `testlab.service` tizim xizmatini avtomatik sozlaydi.

---

## 3. `.env` Konfiguratsiyasini To'ldirish

`.env` faylini oching va sozlamalarni kiriting:

```bash
nano .env
```

Eng muhim parametrlar:
```env
BOT_TOKEN=123456789:AAEhBOweik6ad9r_QwErTy...   # @BotFather dan olingan token
ADMIN_IDS=123456789,987654321                    # Administratorlar Telegram ID lari
SUPER_ADMIN_IDS=123456789                        # Bosh admin

# Agar alohida domeningiz bo'lsa:
WEBAPP_ENABLED=true
WEBAPP_HOST=0.0.0.0
WEBAPP_PORT=8088
WEBAPP_URL=https://testlab.sizningdomeningiz.uz
WEBAPP_AUTO_TUNNEL=false

# Ma'lumotlar bazasi (standart SQLite yoki PostgreSQL):
DATABASE_URL=sqlite+aiosqlite:///data/testlab.db
# PostgreSQL uchun:
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/testlab_db
```

Faylni saqlash: `Ctrl + O` -> `Enter` -> `Ctrl + X`.

---

## 4. Nginx va SSL Sertifikatini Sozlash (Telegram Mini App uchun)

Telegram Mini App **majburiy tartibda HTTPS** protokolini talab qiladi.

1. Nginx o'rnatish:
   ```bash
   sudo apt install -y nginx certbot python3-certbot-nginx
   ```

2. SSL sertifikatini olish:
   ```bash
   sudo certbot --nginx -d testlab.sizningdomeningiz.uz
   ```

3. Nginx konfiguratsiyasini ulash:
   `deploy/nginx.conf` faylidan nusxa olib, server domeniga moslang:
   ```bash
   sudo cp deploy/nginx.conf /etc/nginx/sites-available/testlab.conf
   sudo nano /etc/nginx/sites-available/testlab.conf # domenni o'zgartiring
   sudo ln -s /etc/nginx/sites-available/testlab.conf /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

---

## 5. Botni Ishga Tushirish va Boshqarish (Systemd)

Botni server xizmati sifatida ishga tushiring:

```bash
# Botni ishga tushirish
sudo systemctl start testlab

# Holatini tekshirish (yashil 'active (running)' bo'lishi kerak)
sudo systemctl status testlab

# Server qayta yoqilganda (reboot) avtomatik yonishi uchun:
sudo systemctl enable testlab

# Botni to'xtatish yoki qayta ishga tushirish:
sudo systemctl stop testlab
sudo systemctl restart testlab
```

---

## 6. Loglarni Kuzatish (Monitoring)

Botning ishlash jarayonini jonli kuzatish uchun:

```bash
# Systemd orqali jonli loglar
sudo journalctl -u testlab -f

# Yoki loyihadagi log fayllarini ko'rish
tail -f logs/testlab.log
```

---

## 7. Docker orqali Joylashtirish (Muqobil variant)

Agar Docker afzal bo'lsa:

```bash
cd deploy
docker compose up -d --build
```
Loglarni ko'rish:
```bash
docker compose logs -f
```
