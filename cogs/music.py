"""
cogs/music.py
─────────────
Cog de música para el bot de Discord.

Arquitectura de audio (pipeline probado):
  yt-dlp (subprocess, stdout) ──pipe──► FFmpeg (stdin → PCM) ──► Discord

  • yt-dlp corre como proceso separado y transmite el audio por stdout.
  • FFmpeg lee ese stream por stdin y lo convierte a PCM crudo (s16le).
  • discord.py envía el PCM al canal de voz.

  Ventajas frente a pasar una URL directamente a FFmpeg:
    - No hay URLs que expiren.
    - No hay headers HTTP que formatear ni problemas de autenticación.
    - Funciona con cualquier formato que yt-dlp soporte.

Comandos:
  !play <url/búsqueda>  — reproduce o añade a la cola
  !pause                — pausa la reproducción
  !resume               — reanuda la reproducción
  !skip                 — salta la canción actual
  !stop                 — detiene y limpia la cola
  !queue / !q           — muestra la cola de reproducción
  !nowplaying / !np     — muestra la canción actual
  !shuffle              — mezcla aleatoriamente la cola
  !leave                — desconecta el bot del canal de voz
"""

from __future__ import annotations

import asyncio
import logging
import random
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

import discord
import yt_dlp
from discord.ext import commands

import config

log = logging.getLogger("music")


# ═══════════════════════════════════════════════════════
#  Modelo de canción
# ═══════════════════════════════════════════════════════

@dataclass
class Song:
    """Metadatos de una canción. El audio se transmite al momento de reproducir."""
    webpage_url: str        # URL permanente de YouTube
    title: str
    duration: int           # segundos
    thumbnail: str
    requester: discord.Member

    @property
    def duration_str(self) -> str:
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def to_embed(self, title: str = "Reproduciendo ahora") -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=f"[{self.title}]({self.webpage_url})",
            color=discord.Color.red(),
        )
        embed.set_thumbnail(url=self.thumbnail)
        embed.add_field(name="Duración", value=self.duration_str, inline=True)
        embed.add_field(
            name="Solicitado por", value=self.requester.mention, inline=True
        )
        return embed


# ═══════════════════════════════════════════════════════
#  Fuente de audio: yt-dlp → FFmpeg (pipe)
# ═══════════════════════════════════════════════════════

class YTDLStreamSource(discord.PCMVolumeTransformer):
    """
    Fuente de audio que conecta yt-dlp directamente con FFmpeg via pipe.

    Pipeline:
      yt-dlp --output - <url>   →  proc.stdout
                                      ↓
      discord.FFmpegPCMAudio(proc.stdout, pipe=True)
                                      ↓
             Discord (PCM s16le 48 kHz estéreo)
    """

    def __init__(
        self,
        ffmpeg_source: discord.FFmpegPCMAudio,
        ytdl_proc: subprocess.Popen,
        volume: float = 0.5,
    ) -> None:
        super().__init__(ffmpeg_source, volume)
        self._ytdl_proc = ytdl_proc

    def cleanup(self) -> None:
        """Cierra FFmpeg y mata el proceso de yt-dlp al terminar."""
        super().cleanup()
        try:
            if self._ytdl_proc.poll() is None:
                self._ytdl_proc.kill()
                self._ytdl_proc.wait(timeout=3)
        except Exception:
            pass

    @classmethod
    async def create(cls, webpage_url: str, volume: float = 0.5) -> "YTDLStreamSource":
        """Crea la fuente de forma asíncrona (Popen corre en executor)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, cls._create_sync, webpage_url, volume
        )

    @classmethod
    def _create_sync(cls, webpage_url: str, volume: float) -> "YTDLStreamSource":
        """
        Inicia yt-dlp como subproceso que escribe audio a stdout,
        y conecta ese stdout como stdin de FFmpeg.
        Se ejecuta en un thread executor para no bloquear el event loop.
        """
        ytdl_proc = subprocess.Popen(
            [
                sys.executable, "-m", "yt_dlp",
                "--format", "bestaudio/best",
                "--output", "-",        # transmitir audio a stdout
                "--quiet",
                "--no-warnings",
                "--no-playlist",        # solo el video indicado
                webpage_url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        ffmpeg_source = discord.FFmpegPCMAudio(
            ytdl_proc.stdout,
            pipe=True,
            options="-vn",              # sin stream de video
        )

        return cls(ffmpeg_source, ytdl_proc, volume)


# ═══════════════════════════════════════════════════════
#  Extractor de metadatos (yt-dlp Python API)
# ═══════════════════════════════════════════════════════

_META_OPTS: dict = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": "in_playlist",  # metadatos rápidos para playlists
    "age_limit": None,
}


class YTDLSource:
    """Extrae metadatos de YouTube con yt-dlp (sin descargar audio)."""

    @staticmethod
    async def search(query: str, requester: discord.Member) -> list[Song]:
        """
        Acepta URL de YouTube (video o playlist) o texto de búsqueda.
        Devuelve lista de Song con metadatos solamente.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, YTDLSource._extract_meta, query, requester
        )

    @staticmethod
    def _extract_meta(query: str, requester: discord.Member) -> list[Song]:
        """Extracción de metadatos — bloqueante, corre en executor."""
        is_url = query.startswith(("http://", "https://"))
        if not is_url:
            query = f"ytsearch:{query}"

        with yt_dlp.YoutubeDL(dict(_META_OPTS)) as ydl:
            try:
                info = ydl.extract_info(query, download=False)
            except yt_dlp.utils.DownloadError as exc:
                raise commands.CommandError(
                    f"No se pudo obtener información: {exc}"
                ) from exc

        entries = list(info.get("entries") or [info])

        songs: list[Song] = []
        for entry in entries:
            if not entry:
                continue

            webpage_url = entry.get("webpage_url") or entry.get("url", "")
            if not webpage_url or not webpage_url.startswith("http"):
                continue

            # Thumbnail puede ser str o list de dicts
            thumbnail = entry.get("thumbnail") or ""
            if isinstance(thumbnail, list) and thumbnail:
                last = thumbnail[-1]
                thumbnail = last.get("url", "") if isinstance(last, dict) else str(last)

            songs.append(Song(
                webpage_url=webpage_url,
                title=entry.get("title") or "Título desconocido",
                duration=int(entry.get("duration") or 0),
                thumbnail=thumbnail,
                requester=requester,
            ))

        return songs


# ═══════════════════════════════════════════════════════
#  Estado del reproductor por servidor (guild)
# ═══════════════════════════════════════════════════════

@dataclass
class GuildPlayer:
    """Estado del reproductor para un servidor."""
    voice_client: Optional[discord.VoiceClient] = None
    current: Optional[Song] = None
    queue: list[Song] = field(default_factory=list)
    text_channel: Optional[discord.TextChannel] = None
    _loop_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def is_playing(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_playing()

    def is_paused(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_paused()

    def is_connected(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_connected()

    def clear(self) -> None:
        """Limpia la cola y cancela el loop de reproducción."""
        self.queue.clear()
        self.current = None
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._loop_task = None


# ═══════════════════════════════════════════════════════
#  Cog de música
# ═══════════════════════════════════════════════════════

class Music(commands.Cog, name="Música"):
    """Comandos de reproducción de música desde YouTube."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._players: dict[int, GuildPlayer] = {}

    # ── Helpers internos ────────────────────────────────

    def _get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self._players:
            self._players[guild_id] = GuildPlayer()
        return self._players[guild_id]

    async def _ensure_voice(self, ctx: commands.Context) -> bool:
        """Verifica que el usuario esté en voz y conecta el bot si hace falta."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(
                "Debes estar en un canal de voz para usar este comando."
            )
            return False

        player = self._get_player(ctx.guild.id)
        channel = ctx.author.voice.channel

        if not player.is_connected():
            try:
                player.voice_client = await channel.connect()
            except discord.ClientException:
                await ctx.send("No se pudo conectar al canal de voz.")
                return False
        elif player.voice_client.channel != channel:
            await player.voice_client.move_to(channel)

        player.text_channel = ctx.channel
        return True

    def _start_player(self, guild_id: int) -> None:
        """Inicia el loop de reproducción si no está corriendo ya."""
        player = self._get_player(guild_id)
        if player._loop_task is None or player._loop_task.done():
            player._loop_task = self.bot.loop.create_task(
                self._player_loop(guild_id)
            )

    async def _player_loop(self, guild_id: int) -> None:
        """
        Loop asíncrono que gestiona la cola de reproducción.

        Para cada canción:
          1. Inicia el pipeline yt-dlp → FFmpeg.
          2. Envía embed "Reproduciendo ahora" al canal de texto.
          3. Espera a que FFmpeg termine (o sea interrumpido).
          4. Pasa a la siguiente canción.
        """
        player = self._get_player(guild_id)

        while player.queue and player.is_connected():
            song = player.queue.pop(0)
            player.current = song

            # Crear fuente de audio (yt-dlp → FFmpeg pipe)
            try:
                source = await YTDLStreamSource.create(song.webpage_url)
            except Exception as exc:
                log.error("Error creando fuente para '%s': %s", song.title, exc)
                if player.text_channel:
                    await player.text_channel.send(
                        f"No se pudo reproducir **{song.title}**: {exc}"
                    )
                continue

            # Notificar en el canal de texto
            if player.text_channel:
                await player.text_channel.send(embed=song.to_embed())

            # Evento para saber cuándo termina la canción
            done_event = asyncio.Event()

            def after(
                error: Optional[Exception],
                ev: asyncio.Event = done_event,
            ) -> None:
                if error:
                    log.error(
                        "Error en reproducción de '%s': %s", song.title, error
                    )
                self.bot.loop.call_soon_threadsafe(ev.set)

            player.voice_client.play(source, after=after)

            # Esperar a que termine la canción (o sea saltada/detenida)
            try:
                await done_event.wait()
            except asyncio.CancelledError:
                # stop() o leave() cancelaron el loop — salir limpiamente
                return

        player.current = None

    # ── Comandos ─────────────────────────────────────────

    @commands.command(
        name="play",
        aliases=["p"],
        help="Reproduce una canción o la añade a la cola.",
        usage="<URL de YouTube o texto de búsqueda>",
    )
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """
        Reproduce una URL de YouTube (video o playlist) o busca
        una canción por texto.
        """
        if not await self._ensure_voice(ctx):
            return

        player = self._get_player(ctx.guild.id)

        async with ctx.typing():
            try:
                songs = await YTDLSource.search(query, ctx.author)
            except commands.CommandError as exc:
                await ctx.send(str(exc))
                return

        if not songs:
            await ctx.send("No se encontraron resultados para esa búsqueda.")
            return

        available = config.MAX_QUEUE_SIZE - len(player.queue)
        songs = songs[:available]

        already_active = player.is_playing() or player.is_paused()

        if len(songs) == 1:
            song = songs[0]
            player.queue.append(song)
            if already_active:
                embed = song.to_embed(title="Añadido a la cola")
                embed.add_field(
                    name="Posición en cola",
                    value=str(len(player.queue)),
                    inline=True,
                )
                await ctx.send(embed=embed)
        else:
            player.queue.extend(songs)
            await ctx.send(
                f"Se añadieron **{len(songs)}** canciones a la cola."
            )

        self._start_player(ctx.guild.id)

    @commands.command(
        name="pause",
        help="Pausa la reproducción actual.",
    )
    @commands.guild_only()
    async def pause(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)
        if player.is_playing():
            player.voice_client.pause()
            await ctx.send("Reproducción pausada.")
        else:
            await ctx.send("No hay nada reproduciéndose en este momento.")

    @commands.command(
        name="resume",
        aliases=["r"],
        help="Reanuda la reproducción si está pausada.",
    )
    @commands.guild_only()
    async def resume(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)
        if player.is_paused():
            player.voice_client.resume()
            await ctx.send("Reproducción reanudada.")
        else:
            await ctx.send("La reproducción no está pausada.")

    @commands.command(
        name="skip",
        aliases=["s", "next"],
        help="Salta la canción actual y reproduce la siguiente.",
    )
    @commands.guild_only()
    async def skip(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)
        if not player.is_playing() and not player.is_paused():
            await ctx.send("No hay nada reproduciéndose en este momento.")
            return
        # Detener FFmpeg → after() → done_event.set() → loop avanza
        player.voice_client.stop()
        await ctx.send("Canción saltada.")

    @commands.command(
        name="stop",
        help="Detiene la reproducción y limpia la cola.",
    )
    @commands.guild_only()
    async def stop(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)
        if not player.is_connected():
            await ctx.send("El bot no está en ningún canal de voz.")
            return
        player.clear()
        player.voice_client.stop()
        await ctx.send("Reproducción detenida y cola limpiada.")

    @commands.command(
        name="queue",
        aliases=["q", "cola"],
        help="Muestra las canciones en la cola de reproducción.",
    )
    @commands.guild_only()
    async def queue_list(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)

        if not player.current and not player.queue:
            await ctx.send("La cola está vacía.")
            return

        embed = discord.Embed(
            title="Cola de reproducción",
            color=discord.Color.blurple(),
        )

        if player.current:
            embed.add_field(
                name="Reproduciendo ahora",
                value=(
                    f"[{player.current.title}]({player.current.webpage_url}) "
                    f"— `{player.current.duration_str}` "
                    f"({player.current.requester.mention})"
                ),
                inline=False,
            )

        if player.queue:
            visible = player.queue[:10]
            lines = [
                f"`{i + 1}.` [{s.title}]({s.webpage_url}) "
                f"— `{s.duration_str}` ({s.requester.mention})"
                for i, s in enumerate(visible)
            ]
            if len(player.queue) > 10:
                lines.append(f"_...y {len(player.queue) - 10} más._")
            embed.add_field(
                name=f"En cola — {len(player.queue)} canción(es)",
                value="\n".join(lines),
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(
        name="nowplaying",
        aliases=["np", "current", "ahora"],
        help="Muestra la canción que se está reproduciendo ahora.",
    )
    @commands.guild_only()
    async def nowplaying(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)
        if not player.current:
            await ctx.send("No hay ninguna canción reproduciéndose.")
            return
        await ctx.send(embed=player.current.to_embed())

    @commands.command(
        name="shuffle",
        aliases=["mezclar"],
        help="Mezcla aleatoriamente las canciones en la cola.",
    )
    @commands.guild_only()
    async def shuffle(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)
        if len(player.queue) < 2:
            await ctx.send(
                "Necesitas al menos 2 canciones en la cola para mezclar."
            )
            return
        random.shuffle(player.queue)
        await ctx.send(
            f"Cola mezclada aleatoriamente ({len(player.queue)} canciones)."
        )

    @commands.command(
        name="leave",
        aliases=["disconnect", "dc", "salir"],
        help="Desconecta el bot del canal de voz.",
    )
    @commands.guild_only()
    async def leave(self, ctx: commands.Context) -> None:
        player = self._get_player(ctx.guild.id)
        if not player.is_connected():
            await ctx.send("El bot no está en ningún canal de voz.")
            return
        player.clear()
        await player.voice_client.disconnect()
        player.voice_client = None
        await ctx.send("Desconectado del canal de voz.")

    # ── Manejo de errores del Cog ────────────────────────

    @play.error
    async def play_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                f"Uso: `{config.COMMAND_PREFIX}play <URL o búsqueda>`\n"
                "Ejemplo: `!play https://youtu.be/dQw4w9WgXcQ`"
            )
        else:
            await ctx.send(f"Error al reproducir: {error}")
            log.error("Error en !play: %s", error)


# ═══════════════════════════════════════════════════════
#  Setup del Cog
# ═══════════════════════════════════════════════════════

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
