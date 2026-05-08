import asyncio
import logging
import sys

import discord
from discord.ext import commands

import config

# ── Logging ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bot")


# ── Intents ──────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True   # necesario para leer el contenido de mensajes


# ── Bot ──────────────────────────────────────────────
class MusicBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=config.COMMAND_PREFIX,
            intents=intents,
            help_command=commands.DefaultHelpCommand(no_category="Comandos"),
        )

    async def setup_hook(self) -> None:
        """Carga los cogs al iniciar el bot."""
        await self.load_extension("cogs.music")
        log.info("Cog 'music' cargado correctamente.")

    async def on_ready(self) -> None:
        log.info("Bot conectado como %s (ID: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"{config.COMMAND_PREFIX}play",
            )
        )

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Manejo global de errores de comandos."""
        if isinstance(error, commands.CommandNotFound):
            return  # ignorar comandos desconocidos silenciosamente

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                f"Faltan argumentos. Usa `{config.COMMAND_PREFIX}help {ctx.command}` "
                "para ver el uso correcto."
            )
            return

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Este comando solo puede usarse en un servidor.")
            return

        # Para el resto, propagar al handler del cog si lo hay
        if hasattr(ctx.command, "on_error"):
            return

        log.error("Error no manejado en el comando '%s': %s", ctx.command, error)


# ── Punto de entrada ─────────────────────────────────
async def main() -> None:
    async with MusicBot() as bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot detenido por el usuario.")
