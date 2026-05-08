import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot ──────────────────────────────────────────────
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")

# ── Validación temprana ──────────────────────────────
if not DISCORD_TOKEN or DISCORD_TOKEN == "tu_token_aqui":
    raise ValueError(
        "No se encontró un DISCORD_TOKEN válido.\n"
        "Copia .env.example como .env y rellena tu token."
    )

# ── Opciones de yt-dlp ───────────────────────────────
YTDL_OPTIONS: dict = {
    "format": "bestaudio/best",
    "noplaylist": False,          # permite reproducir playlists
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch", # buscar en YouTube si no es una URL
    "source_address": "0.0.0.0",  # evitar problemas de IPv6
    "cookiefile": None,           # opcional: ruta a cookies.txt de YouTube
    "age_limit": None,            # sin restricciones de edad
    "postprocessors": [],
}

# ── Opciones de FFmpeg ───────────────────────────────
FFMPEG_OPTIONS: dict = {
    "before_options": (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    ),
    "options": "-vn",             # solo audio, sin video
}

# ── Límites del reproductor ──────────────────────────
MAX_QUEUE_SIZE: int = 100        # máximo de canciones en la cola
