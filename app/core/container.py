from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.integrations import AsyncHttpClient, DiscordOrchestratedTimeoutPolicy
from app.repositories.postgres_database import PostgresDatabase
from app.repositories.postgres_repositories import (
    PostgresBolaoRepository,
    PostgresEconomyRepository,
    PostgresFormRepository,
    PostgresGameProgressRepository,
    PostgresGiveawayRepository,
    PostgresMatchBetRepository,
    PostgresTrucoRepository,
    PostgresUnoRepository,
)
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
from app.services.truco_service import TrucoService
from app.services.uno_service import UnoService


@dataclass(slots=True)
class AppContainer:
    """Raiz de composicao das dependencias do bot."""

    postgres_database: PostgresDatabase
    http_client: AsyncHttpClient
    giveaway_repository: PostgresGiveawayRepository
    bolao_repository: PostgresBolaoRepository
    match_bet_repository: PostgresMatchBetRepository
    truco_repository: PostgresTrucoRepository
    uno_repository: PostgresUnoRepository
    game_progress_repository: PostgresGameProgressRepository
    form_repository: PostgresFormRepository
    economy_repository: PostgresEconomyRepository
    giveaway_service: GiveawayService
    bolao_service: BolaoService
    form_service: FormService
    economy_service: EconomyService
    game_progress_service: GameProgressService
    match_bet_service: MatchBetService
    truco_service: TrucoService
    uno_service: UnoService
    activity_service: ActivityService
    shop_service: ShopService
    casino_service: CasinoService
    blackjack_service: BlackjackService
    scratch_card_service: ScratchCardService
    collective_race_service: CollectiveRaceService

    @classmethod
    def build(cls, settings: Settings) -> AppContainer:
        database = PostgresDatabase(
            settings.POSTGRES_DSN,
            schema=settings.POSTGRES_SCHEMA,
            min_size=settings.POSTGRES_POOL_MIN_SIZE,
            max_size=settings.POSTGRES_POOL_MAX_SIZE,
        )
        economy_repository = PostgresEconomyRepository(database)
        game_progress_repository = PostgresGameProgressRepository(database)
        match_bet_repository = PostgresMatchBetRepository(database)
        truco_repository = PostgresTrucoRepository(database)
        uno_repository = PostgresUnoRepository(database)
        giveaway_repository = PostgresGiveawayRepository(database)
        bolao_repository = PostgresBolaoRepository(database)
        form_repository = PostgresFormRepository(database)

        economy_service = EconomyService(economy_repository)
        game_progress_service = GameProgressService(
            game_progress_repository,
            economy_repository,
        )
        match_bet_service = MatchBetService(
            match_bet_repository,
            economy_repository,
        )
        truco_service = TrucoService(
            truco_repository,
            economy_repository,
            progress_service=game_progress_service,
        )
        uno_service = UnoService(uno_repository, economy_repository)
        policy = DiscordOrchestratedTimeoutPolicy(
            interaction_ack_seconds=settings.DISCORD_INTERACTION_ACK_SECONDS,
            connect_seconds=settings.HTTP_CONNECT_TIMEOUT_SECONDS,
            request_seconds=settings.HTTP_REQUEST_TIMEOUT_SECONDS,
            max_retries=settings.HTTP_MAX_RETRIES,
        )
        return cls(
            postgres_database=database,
            http_client=AsyncHttpClient(
                policy,
                access_log_enabled=settings.ENABLE_NETWORK_ACCESS_LOG,
            ),
            giveaway_repository=giveaway_repository,
            bolao_repository=bolao_repository,
            match_bet_repository=match_bet_repository,
            truco_repository=truco_repository,
            uno_repository=uno_repository,
            game_progress_repository=game_progress_repository,
            form_repository=form_repository,
            economy_repository=economy_repository,
            giveaway_service=GiveawayService(giveaway_repository),
            bolao_service=BolaoService(bolao_repository),
            form_service=FormService(form_repository),
            economy_service=economy_service,
            game_progress_service=game_progress_service,
            match_bet_service=match_bet_service,
            truco_service=truco_service,
            uno_service=uno_service,
            activity_service=ActivityService(economy_repository),
            shop_service=ShopService(economy_repository),
            casino_service=CasinoService(
                economy_repository,
                progress_service=game_progress_service,
            ),
            blackjack_service=BlackjackService(
                economy_repository,
                progress_service=game_progress_service,
            ),
            scratch_card_service=ScratchCardService(
                economy_repository,
                game_progress_service,
            ),
            collective_race_service=CollectiveRaceService(
                game_progress_repository,
                economy_repository,
                game_progress_service,
            ),
        )

    async def open(self) -> None:
        await self.http_client.open()

    async def close(self) -> None:
        await self.http_client.close()
        await self.postgres_database.close()
