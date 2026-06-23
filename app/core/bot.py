from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.repositories.giveaway_repository import SQLiteGiveawayRepository
from app.services.giveaway_service import GiveawayService

logger = logging.getLogger(__name__)


class DiscordBot(commands.Bot):
    """Classe principal do bot."""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.giveaway_repository = SQLiteGiveawayRepository(settings.GIVEAWAY_DB_PATH)
        self.giveaway_service = GiveawayService(self.giveaway_repository)

        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = settings.ENABLE_MEMBERS_INTENT
        intents.moderation = True
        intents.message_content = settings.ENABLE_MESSAGE_CONTENT_INTENT

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        """
        Executado antes do bot ficar online.
        Ideal para carregar extensoes e sincronizar slash commands.
        """
        setup_logging()
        logger.info("Iniciando setup do bot...")

        await self.load_all_extensions()
        await self.sync_commands()

    async def load_all_extensions(self) -> None:
        """
        Carrega automaticamente todos os Cogs da pasta app/cogs.
        Apenas arquivos .py com setup() sao carregados como extensoes.
        """
        project_root = Path(__file__).resolve().parents[2]
        cogs_path = project_root / "app" / "cogs"

        for file in cogs_path.rglob("*.py"):
            if file.name.startswith("__") or not self._has_setup_function(file):
                continue

            module = ".".join(file.relative_to(project_root).with_suffix("").parts)
            try:
                await self.load_extension(module)
                logger.info("Cog carregado com sucesso: %s", module)
            except Exception as exc:
                logger.exception("Erro ao carregar Cog %s: %s", module, exc)

    @staticmethod
    def _has_setup_function(file: Path) -> bool:
        source = file.read_text(encoding="utf-8")
        return "def setup(" in source or "async def setup(" in source

    async def sync_commands(self) -> None:
        """
        Sincroniza os Slash Commands.
        Em desenvolvimento: sincroniza no servidor de testes para ser mais rapido.
        Em producao: sincroniza globalmente.
        """
        settings = get_settings()

        try:
            if settings.GUILD_ID:
                guild = discord.Object(id=settings.GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(
                    "Slash Commands sincronizados no servidor de testes (%s): "
                    "%s comando(s).",
                    settings.GUILD_ID,
                    len(synced),
                )
            else:
                synced = await self.tree.sync()
                logger.info(
                    "Slash Commands sincronizados globalmente: %s comando(s).",
                    len(synced),
                )
        except discord.Forbidden as exc:
            logger.error(
                "Nao foi possivel sincronizar Slash Commands no servidor %s: %s. "
                "Verifique se GUILD_ID aponta para um servidor onde o bot esta "
                "presente e se ele foi convidado com o escopo applications.commands.",
                settings.GUILD_ID,
                exc,
            )
        except Exception as exc:
            logger.exception("Erro ao sincronizar Slash Commands: %s", exc)
