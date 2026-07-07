from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.repositories.bolao_repository import SQLiteBolaoRepository
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.repositories.form_repository import SQLiteFormRepository
from app.repositories.game_progress_repository import SQLiteGameProgressRepository
from app.repositories.giveaway_repository import SQLiteGiveawayRepository
from app.repositories.match_bet_repository import SQLiteMatchBetRepository
from app.services.activity_service import ActivityService
from app.services.blackjack_service import BlackjackService
from app.services.bolao_service import BolaoService
from app.services.casino_service import CasinoService
from app.services.collective_race_service import CollectiveRaceService
from app.services.economy_service import EconomyService
from app.services.form_service import FormService
from app.services.game_progress_service import GameProgressService
from app.services.giveaway_service import GiveawayService
from app.services.match_bet_service import MatchBetService
from app.services.scratch_card_service import ScratchCardService
from app.services.shop_service import ShopService

logger = logging.getLogger(__name__)


class DiscordBot(commands.Bot):
    """Classe principal do bot."""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.giveaway_repository = SQLiteGiveawayRepository(settings.GIVEAWAY_DB_PATH)
        self.giveaway_service = GiveawayService(self.giveaway_repository)
        self.bolao_repository = SQLiteBolaoRepository(settings.BOLAO_DB_PATH)
        self.bolao_service = BolaoService(self.bolao_repository)
        self.match_bet_repository = SQLiteMatchBetRepository(settings.MATCH_BET_DB_PATH)
        self.game_progress_repository = SQLiteGameProgressRepository(
            settings.GAME_PROGRESS_DB_PATH
        )
        self.form_repository = SQLiteFormRepository(settings.FORM_DB_PATH)
        self.form_service = FormService(self.form_repository)
        self.economy_repository = SQLiteEconomyRepository(settings.ECONOMY_DB_PATH)
        self.economy_service = EconomyService(self.economy_repository)
        self.game_progress_service = GameProgressService(
            self.game_progress_repository,
            self.economy_repository,
        )
        self.match_bet_service = MatchBetService(
            self.match_bet_repository,
            self.economy_repository,
        )
        self.activity_service = ActivityService(self.economy_repository)
        self.shop_service = ShopService(self.economy_repository)
        self.casino_service = CasinoService(self.economy_repository)
        self.blackjack_service = BlackjackService(self.economy_repository)
        self.scratch_card_service = ScratchCardService(
            self.economy_repository,
            self.game_progress_service,
        )
        self.collective_race_service = CollectiveRaceService(
            self.game_progress_repository,
            self.economy_repository,
            self.game_progress_service,
        )

        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.voice_states = True
        intents.members = settings.ENABLE_MEMBERS_INTENT
        intents.moderation = True
        intents.message_content = settings.ENABLE_MESSAGE_CONTENT_INTENT

        super().__init__(
            command_prefix="cp!",
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
