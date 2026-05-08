# ============================================================
#  Dockerfile — Discord Music Bot
#  Build: docker build -t discord-bot .
#  Run:   docker compose up -d
# ============================================================

FROM python:3.12-slim

# ── Dependencias del sistema ──────────────────────────────────
# ffmpeg : procesamiento de audio
# git    : necesario para instalar discord.py desde GitHub
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
    && rm -rf /var/lib/apt/lists/*

# ── Usuario no-root ──────────────────────────────────────────
RUN useradd -m -u 1000 botuser

WORKDIR /app

# ── Dependencias Python ──────────────────────────────────────
# Se copia primero solo requirements.txt para aprovechar la caché
# de Docker: la imagen solo se reconstruye si cambian las deps.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Código de la aplicación ───────────────────────────────────
COPY . .

# ── Cambiar al usuario sin privilegios ────────────────────────
USER botuser

# ── Comando de inicio ─────────────────────────────────────────
CMD ["python", "bot.py"]
