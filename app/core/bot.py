from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from app.core.config import get_settings
from app.core.container import AppContainer
from app.core.logger import setup_logging
from app.integrations import build_http_trace_config

logger = logging.getLogger(__name__)


class DiscordBot(commands.Bot):
    """Classe principal do bot."""

    def __init__(self) -> None:
        settings = get_settings()
        setup_logging()
        self.settings = settings
        self.container = AppContainer.build(settings)
        self._expose_container_dependencies()

        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.voice_states = True
        intents.members = settings.ENABLE_MEMBERS_INTENT
        intents.moderation = True
        intents.message_content = settings.ENABLE_MESSAGE_CONTENT_INTENT

        http_trace = build_http_trace_config(enabled=settings.ENABLE_NETWORK_ACCESS_LOG)
        super().__init__(
            command_prefix="cp!",
            intents=intents,
            help_command=None,
            http_trace=http_trace,
        )

    def _expose_container_dependencies(self) -> None:
        """Mantem a API esperada pelos cogs durante a reorganizacao interna."""

        for name in self.container.__dataclass_fields__:
            setattr(self, name, getattr(self.container, name))
        logger.info("Runtime de persistencia: PostgreSQL exclusivo.")

    async def setup_hook(self) -> None:
        """
        Executado antes do bot ficar online.
        Ideal para carregar extensoes e sincronizar slash commands.
        """
        logger.info("Iniciando setup do bot...")
        await self.container.open()

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

    async def close(self) -> None:
        try:
            await super().close()
        finally:
            await self.container.close()

    async def on_connect(self) -> None:
        logger.info("network.discord.gateway.connected")

    async def on_disconnect(self) -> None:
        logger.warning("network.discord.gateway.disconnected")

    async def on_resumed(self) -> None:
        logger.info("network.discord.gateway.resumed")

    async def on_socket_event_type(self, event_type: str) -> None:
        logger.debug("network.discord.gateway.event type=%s", event_type)

    async def sync_commands(self) -> None:
        """
        Sincroniza os Slash Commands.
        Sem GUILD_IDS, sincroniza globalmente para funcionar em qualquer servidor.
        GUILD_IDS e destinado apenas a sincronizacao rapida em homologacao.
        """
        settings = get_settings()

        try:
            if settings.GUILD_IDS:
                total = 0
                for guild_id in settings.GUILD_IDS:
                    guild = discord.Object(id=guild_id)
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    total += len(synced)
                logger.info(
                    "Slash Commands sincronizados em %s servidor(es) de testes: "
                    "%s registro(s).",
                    len(settings.GUILD_IDS),
                    total,
                )
            else:
                synced = await self.tree.sync()
                logger.info(
                    "Slash Commands sincronizados globalmente: %s comando(s).",
                    len(synced),
                )
        except discord.Forbidden as exc:
            logger.error(
                "Nao foi possivel sincronizar Slash Commands nos servidores %s: %s. "
                "Verifique se GUILD_IDS aponta para servidores onde o bot esta "
                "presente e se ele foi convidado com o escopo applications.commands.",
                settings.GUILD_IDS,
                exc,
            )
        except Exception as exc:
            logger.exception("Erro ao sincronizar Slash Commands: %s", exc)
