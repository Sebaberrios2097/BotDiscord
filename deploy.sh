#!/usr/bin/env bash
# =============================================================
#  deploy.sh — Script de despliegue inicial para Ubuntu
#
#  Ejecutar UNA SOLA VEZ en el servidor para dejar todo listo.
#  Uso:
#    chmod +x deploy.sh
#    ./deploy.sh
# =============================================================
set -euo pipefail

# ── Colores para output legible ───────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Variables — editar antes de ejecutar ─────────────────────
BOT_USER="${BOT_USER:-$USER}"                       # usuario que correrá el bot
BOT_DIR="${BOT_DIR:-/home/$BOT_USER/BotDiscord}"    # directorio del proyecto
REPO_URL="${REPO_URL:-}"                            # URL del repo GitHub (HTTPS o SSH)
PYTHON_BIN="python3"

# =============================================================
#  1. Dependencias del sistema
# =============================================================
info "Actualizando lista de paquetes..."
sudo apt-get update -qq

info "Instalando dependencias del sistema..."
sudo apt-get install -y -qq \
    git \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg

info "Versiones instaladas:"
$PYTHON_BIN --version
ffmpeg -version 2>&1 | head -1
git --version

# =============================================================
#  2. Clonar el repositorio (si no existe)
# =============================================================
if [ -d "$BOT_DIR/.git" ]; then
    warn "El directorio $BOT_DIR ya existe. Actualizando con git pull..."
    git -C "$BOT_DIR" pull origin main
else
    if [ -z "$REPO_URL" ]; then
        error "Debes definir REPO_URL antes de ejecutar este script.\nEjemplo: REPO_URL=https://github.com/usuario/BotDiscord.git ./deploy.sh"
    fi
    info "Clonando repositorio en $BOT_DIR..."
    git clone "$REPO_URL" "$BOT_DIR"
fi

# =============================================================
#  3. Entorno virtual + dependencias Python
# =============================================================
info "Creando entorno virtual Python..."
$PYTHON_BIN -m venv "$BOT_DIR/.venv"

info "Instalando dependencias de Python..."
"$BOT_DIR/.venv/bin/pip" install --upgrade pip -q
"$BOT_DIR/.venv/bin/pip" install -r "$BOT_DIR/requirements.txt" -q

# =============================================================
#  4. Archivo .env
# =============================================================
if [ ! -f "$BOT_DIR/.env" ]; then
    cp "$BOT_DIR/.env.example" "$BOT_DIR/.env"
    warn "Archivo .env creado desde .env.example."
    warn "Edita $BOT_DIR/.env con tu DISCORD_TOKEN antes de iniciar el bot."
    warn "  nano $BOT_DIR/.env"
else
    info ".env ya existe. No se sobreescribe."
fi

# =============================================================
#  5. Servicio systemd
# =============================================================
SERVICE_FILE="/etc/systemd/system/discord-bot.service"

info "Instalando servicio systemd..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Discord Music Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$BOT_USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/.venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=discord-bot

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable discord-bot
info "Servicio discord-bot habilitado (se iniciará automáticamente al reiniciar)."

# =============================================================
#  6. Configurar sudo sin contraseña para reiniciar el servicio
#     (necesario para el workflow de GitHub Actions)
# =============================================================
SUDOERS_FILE="/etc/sudoers.d/discord-bot"
info "Configurando sudo para reiniciar el servicio sin contraseña..."
echo "$BOT_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart discord-bot, /bin/systemctl is-active discord-bot" \
    | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 440 "$SUDOERS_FILE"

# =============================================================
#  7. Resumen final
# =============================================================
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  Despliegue inicial completado${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "  Directorio del bot : $BOT_DIR"
echo "  Servicio systemd   : discord-bot"
echo "  Python             : $BOT_DIR/.venv/bin/python"
echo ""
echo "Próximos pasos:"
echo "  1. Edita el token:  nano $BOT_DIR/.env"
echo "  2. Inicia el bot:   sudo systemctl start discord-bot"
echo "  3. Ver logs:        sudo journalctl -u discord-bot -f"
echo ""
