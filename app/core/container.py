from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.integrations import AsyncHttpClient, DiscordOrchestratedTimeoutPolicy
from app.integrations.mlbb import MlbbClient
from app.repositories.mlbb_repository import PostgresMlbbRepository
from app.repositories.postgres_database import PostgresDatabase
from app.repositories.postgres_moderation_repository import PostgresModerationRepository
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
from app.services.economic_tier_service import EconomicTierService
from app.services.economy_limits import EconomicDifficultyPolicyService
from app.services.economy_service import EconomyService
from app.services.form_service import FormService
from app.services.game_progress_service import GameProgressService
from app.services.giveaway_service import GiveawayService
from app.services.match_bet_service import MatchBetService
from app.services.mlbb_auth_service import MlbbAuthService
from app.services.mlbb_cache_service import MlbbCacheService
from app.services.mlbb_profile_service import MlbbProfileService
from app.services.mlbb_token_cipher import MlbbTokenCipher
from app.services.moderation_service import ModerationService
from app.services.scratch_card_service import ScratchCardService
from app.services.shop_service import ShopService
from app.services.truco_service import TrucoService
from app.services.uno_service import UnoService


@dataclass(slots=True)
class AppContainer:
    """Raiz de composicao das dependencias do bot."""

    postgres_database: PostgresDatabase
    http_client: AsyncHttpClient
    mlbb_client: MlbbClient
    mlbb_repository: PostgresMlbbRepository
    mlbb_token_cipher: MlbbTokenCipher
    giveaway_repository: PostgresGiveawayRepository
    bolao_repository: PostgresBolaoRepository
    match_bet_repository: PostgresMatchBetRepository
    truco_repository: PostgresTrucoRepository
    uno_repository: PostgresUnoRepository
    game_progress_repository: PostgresGameProgressRepository
    form_repository: PostgresFormRepository
    economy_repository: PostgresEconomyRepository
    moderation_repository: PostgresModerationRepository
    giveaway_service: GiveawayService
    bolao_service: BolaoService
    form_service: FormService
    economy_service: EconomyService
    moderation_service: ModerationService
    mlbb_auth_service: MlbbAuthService
    mlbb_cache_service: MlbbCacheService
    mlbb_profile_service: MlbbProfileService
    economic_tier_service: EconomicTierService
    economic_difficulty_policy_service: EconomicDifficultyPolicyService
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
        moderation_repository = PostgresModerationRepository(database)
        game_progress_repository = PostgresGameProgressRepository(database)
        match_bet_repository = PostgresMatchBetRepository(database)
        truco_repository = PostgresTrucoRepository(database)
        uno_repository = PostgresUnoRepository(database)
        giveaway_repository = PostgresGiveawayRepository(database)
        bolao_repository = PostgresBolaoRepository(database)
        form_repository = PostgresFormRepository(database)
        mlbb_repository = PostgresMlbbRepository(database)

        economy_service = EconomyService(economy_repository)
        economic_tier_service = EconomicTierService()
        economic_policy_service = EconomicDifficultyPolicyService(
            economy_repository,
            economic_tier_service,
            increased_threshold_bps=settings.ECONOMIC_DIFFICULTY_THRESHOLD_BPS,
        )
        game_progress_service = GameProgressService(
            game_progress_repository,
            economy_repository,
        )
        match_bet_service = MatchBetService(
            match_bet_repository,
            economy_repository,
            economic_policy=economic_policy_service,
        )
        truco_service = TrucoService(
            truco_repository,
            economy_repository,
            progress_service=game_progress_service,
            economic_policy=economic_policy_service,
        )
        uno_service = UnoService(
            uno_repository,
            economy_repository,
            economic_policy=economic_policy_service,
        )
        policy = DiscordOrchestratedTimeoutPolicy(
            interaction_ack_seconds=settings.DISCORD_INTERACTION_ACK_SECONDS,
            connect_seconds=settings.HTTP_CONNECT_TIMEOUT_SECONDS,
            request_seconds=settings.HTTP_REQUEST_TIMEOUT_SECONDS,
            max_retries=settings.HTTP_MAX_RETRIES,
        )
        http_client = AsyncHttpClient(
            policy,
            access_log_enabled=settings.ENABLE_NETWORK_ACCESS_LOG,
        )
        mlbb_client = MlbbClient(
            http_client,
            base_url=settings.MLBB_API_BASE_URL,
            timeout_seconds=settings.MLBB_HTTP_TIMEOUT_SECONDS,
            max_concurrent_requests=settings.MLBB_MAX_CONCURRENT_REQUESTS,
            max_retries=min(settings.HTTP_MAX_RETRIES, 2),
        )
        mlbb_token_cipher = MlbbTokenCipher(
            settings.MLBB_TOKEN_ENCRYPTION_KEYS if settings.MLBB_ENABLED else ()
        )
        mlbb_cache_service = MlbbCacheService(
            profile_ttl_seconds=settings.MLBB_PROFILE_CACHE_TTL_SECONDS,
            stats_ttl_seconds=settings.MLBB_STATS_CACHE_TTL_SECONDS,
            refresh_cooldown_seconds=(settings.MLBB_PROFILE_REFRESH_COOLDOWN_SECONDS),
        )
        mlbb_auth_service = MlbbAuthService(
            mlbb_repository,
            mlbb_client,
            mlbb_token_cipher,
            economy_repository,
            enabled=settings.MLBB_ENABLED,
            auth_ttl_seconds=settings.MLBB_AUTH_TTL_SECONDS,
            send_cooldown_seconds=settings.MLBB_SEND_VC_COOLDOWN_SECONDS,
            max_confirm_attempts=settings.MLBB_MAX_CONFIRM_ATTEMPTS,
            cache_invalidator=mlbb_cache_service,
        )
        mlbb_profile_service = MlbbProfileService(
            mlbb_repository,
            mlbb_client,
            mlbb_token_cipher,
            mlbb_cache_service,
            enabled=settings.MLBB_ENABLED,
        )
        return cls(
            postgres_database=database,
            http_client=http_client,
            mlbb_client=mlbb_client,
            mlbb_repository=mlbb_repository,
            mlbb_token_cipher=mlbb_token_cipher,
            giveaway_repository=giveaway_repository,
            bolao_repository=bolao_repository,
            match_bet_repository=match_bet_repository,
            truco_repository=truco_repository,
            uno_repository=uno_repository,
            game_progress_repository=game_progress_repository,
            form_repository=form_repository,
            economy_repository=economy_repository,
            moderation_repository=moderation_repository,
            giveaway_service=GiveawayService(giveaway_repository),
            bolao_service=BolaoService(bolao_repository),
            form_service=FormService(form_repository),
            economy_service=economy_service,
            moderation_service=ModerationService(moderation_repository),
            mlbb_auth_service=mlbb_auth_service,
            mlbb_cache_service=mlbb_cache_service,
            mlbb_profile_service=mlbb_profile_service,
            economic_tier_service=economic_tier_service,
            economic_difficulty_policy_service=economic_policy_service,
            game_progress_service=game_progress_service,
            match_bet_service=match_bet_service,
            truco_service=truco_service,
            uno_service=uno_service,
            activity_service=ActivityService(economy_repository),
            shop_service=ShopService(economy_repository),
            casino_service=CasinoService(
                economy_repository,
                progress_service=game_progress_service,
                economic_policy=economic_policy_service,
            ),
            blackjack_service=BlackjackService(
                economy_repository,
                progress_service=game_progress_service,
                economic_policy=economic_policy_service,
            ),
            scratch_card_service=ScratchCardService(
                economy_repository,
                game_progress_service,
                economic_policy=economic_policy_service,
            ),
            collective_race_service=CollectiveRaceService(
                game_progress_repository,
                economy_repository,
                game_progress_service,
                economic_policy=economic_policy_service,
            ),
        )

    async def open(self) -> None:
        await self.http_client.open()

    async def close(self) -> None:
        await self.http_client.close()
        await self.postgres_database.close()
