# ==========================================================
#  TestLab — Production Dockerfile
# ==========================================================

FROM python:3.11-slim

# Tizim bog'liqliklari (Pillow, asyncpg, build vositalari)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Avval faqat bog'liqliklarni o'rnatamiz (Docker keshidan foydalanish uchun)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Loyihaning barcha fayllarini ko'chirish
COPY . .

# Ma'lumotlar va loglar papkalari
RUN mkdir -p data logs exports assets/fonts assets/generated

# Mini App porti
EXPOSE 8088

# Botni ishga tushirish
CMD ["python", "run.py"]
