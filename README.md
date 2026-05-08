# Discord Music Bot

Bot de Discord para reproducir música desde YouTube en canales de voz.

## Requisitos previos

### 1. Python

Requiere **Python 3.10 o superior**.

```bash
python --version
```

### 2. FFmpeg

FFmpeg es obligatorio para que el bot procese el audio.

**Windows**
1. Descarga FFmpeg desde https://ffmpeg.org/download.html (build de `gyan.dev` o `BtbN`)
2. Extrae el ZIP y copia la carpeta a `C:\ffmpeg`
3. Añade `C:\ffmpeg\bin` a la variable de entorno `PATH`
4. Verifica con: `ffmpeg -version`

**Linux (Ubuntu/Debian)**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS**
```bash
brew install ffmpeg
```

---

## Instalación

```bash
# 1. Clona o descarga el repositorio
cd BotDiscord

# 2. Crea y activa un entorno virtual (recomendado)
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. Instala las dependencias
pip install -r requirements.txt
```

---

## Configuración

1. Copia el archivo de ejemplo:
   ```bash
   cp .env.example .env
   ```

2. Abre `.env` y rellena tu token:
   ```
   DISCORD_TOKEN=tu_token_real_aqui
   COMMAND_PREFIX=!
   ```

3. **Obtener el token del bot:**
   - Ve a https://discord.com/developers/applications
   - Crea una nueva aplicación → Bot → "Reset Token"
   - Activa los **Privileged Gateway Intents**: `Message Content Intent`

4. **Invitar el bot al servidor:**
   - En el portal de desarrolladores: OAuth2 → URL Generator
   - Scopes: `bot`
   - Bot Permissions: `Connect`, `Speak`, `Send Messages`, `Embed Links`, `Read Message History`
   - Usa la URL generada para invitar al bot

---

## Uso

```bash
python bot.py
```

---

## Comandos

| Comando | Alias | Descripción |
|---|---|---|
| `!play <URL/búsqueda>` | `!p` | Reproduce una canción o la añade a la cola |
| `!pause` | — | Pausa la reproducción |
| `!resume` | `!r` | Reanuda la reproducción |
| `!skip` | `!s`, `!next` | Salta la canción actual |
| `!stop` | — | Detiene la reproducción y limpia la cola |
| `!queue` | `!q`, `!cola` | Muestra la cola de reproducción |
| `!nowplaying` | `!np`, `!ahora` | Muestra la canción actual |
| `!shuffle` | `!mezclar` | Mezcla aleatoriamente la cola |
| `!leave` | `!dc`, `!salir` | Desconecta el bot del canal de voz |

### Ejemplos

```
!play https://www.youtube.com/watch?v=dQw4w9WgXcQ
!play https://www.youtube.com/playlist?list=PLxxxxxx
!play bohemian rhapsody queen
!skip
!q
!np
```

---

## Estructura del proyecto

```
BotDiscord/
├── bot.py          # Punto de entrada del bot
├── config.py       # Configuración y opciones de yt-dlp / FFmpeg
├── .env            # Variables de entorno (NO subir a git)
├── .env.example    # Plantilla de variables de entorno
├── requirements.txt
└── cogs/
    └── music.py    # Lógica completa de reproducción de música
```

---

## Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| `ffmpeg not found` | FFmpeg no está en el PATH | Añadir `bin/` de FFmpeg al PATH del sistema |
| `No se pudo conectar al canal de voz` | Permisos insuficientes | Verificar permisos `Connect` y `Speak` |
| `Token inválido` | Token incorrecto en `.env` | Regenerar el token en el Developer Portal |
| Audio entrecortado | Conexión lenta o CPUbaja | Las opciones de reconexión de FFmpeg ya están configuradas |
