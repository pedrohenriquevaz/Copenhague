from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

from app.integrations.mlbb import (
    MlbbClient,
    MlbbIntegrationError,
    MlbbPlayerProfile,
    MlbbPlayerStatsRaw,
    MlbbSessionExpiredError,
    MlbbUnavailableError,
    resolve_rank_name,
)
from app.models.mlbb import (
    MlbbAccountLink,
    MlbbAccountLinkStatus,
    MlbbAchievement,
    MlbbAchievementsSnapshot,
    MlbbProfileAccess,
    MlbbProfileSnapshot,
    MlbbProfileVisibility,
)
from app.repositories.mlbb_repository import MlbbRepository
from app.services.mlbb_cache_service import (
    MlbbCacheService,
    MlbbRefreshCooldownError,
)
from app.services.mlbb_token_cipher import MlbbTokenCipher, MlbbTokenCipherError
from app.utils.mlbb_formatters import calculate_win_rate, normalize_score

T = TypeVar("T")


class MlbbProfileServiceError(RuntimeError):
    """Erro de produto seguro para consultas de perfil MLBB."""


class MlbbProfileFeatureDisabledError(MlbbProfileServiceError):
    pass


class MlbbProfileNotLinkedError(MlbbProfileServiceError):
    pass


class MlbbProfileReauthenticationRequiredError(MlbbProfileServiceError):
    pass


class MlbbProfileAccessDeniedError(MlbbProfileServiceError):
    pass


class MlbbProfileProviderUnavailableError(MlbbProfileServiceError):
    pass


class MlbbProfileProviderRejectedError(MlbbProfileServiceError):
    pass


class MlbbProfileIdentityMismatchError(MlbbProfileServiceError):
    pass


class MlbbProfileRefreshCooldownError(MlbbProfileServiceError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("A atualização manual está em cooldown.")
        self.retry_after_seconds = retry_after_seconds


class MlbbProfileService:
    """Consulta perfil e estatísticas sem expor a credencial persistida."""

    def __init__(
        self,
        repository: MlbbRepository,
        client: MlbbClient,
        token_cipher: MlbbTokenCipher,
        cache_service: MlbbCacheService,
        *,
        enabled: bool,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if enabled and not token_cipher.configured:
            raise ValueError(
                "MLBB_TOKEN_ENCRYPTION_KEYS é obrigatória com MLBB_ENABLED."
            )
        self._repository = repository
        self._client = client
        self._token_cipher = token_cipher
        self._cache = cache_service
        self._enabled = enabled
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def check_access(
        self,
        *,
        guild_id: int,
        requester_user_id: int,
        target_user_id: int,
    ) -> MlbbProfileAccess:
        link = await self._get_authorized_link(
            guild_id=guild_id,
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
        )
        return MlbbProfileAccess(
            guild_id=guild_id,
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
            visibility=link.visibility,
        )

    async def get_profile(
        self,
        *,
        guild_id: int,
        requester_user_id: int,
        target_user_id: int,
        force_refresh: bool = False,
    ) -> MlbbProfileSnapshot:
        link = await self._get_authorized_link(
            guild_id=guild_id,
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
        )
        self._reserve_refresh_if_requested(
            link=link,
            requester_user_id=requester_user_id,
            force_refresh=force_refresh,
        )
        jwt = self._decrypt_credential(link)

        profile_result = await self._cache.get_profile(
            guild_id=guild_id,
            discord_user_id=target_user_id,
            loader=lambda: self._load_profile(link, jwt),
            force_refresh=force_refresh,
        )
        stats_result = await self._cache.get_stats(
            guild_id=guild_id,
            discord_user_id=target_user_id,
            loader=lambda: self._load_stats(link, jwt),
            force_refresh=force_refresh,
        )
        profile = profile_result.value
        stats = stats_result.value
        current_link = await self._get_authorized_link(
            guild_id=guild_id,
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
        )
        return MlbbProfileSnapshot(
            discord_user_id=target_user_id,
            role_id=profile.role_id,
            zone_id=profile.zone_id,
            player_name=profile.name,
            avatar_url=profile.avatar_url,
            level=profile.level,
            current_rank=resolve_rank_name(profile.current_rank_code),
            highest_rank=resolve_rank_name(profile.highest_rank_code),
            matches=stats.matches,
            wins=stats.wins,
            win_rate=calculate_win_rate(stats.wins, stats.matches),
            mvp_count=stats.mvp_count,
            country_code=profile.country_code,
            visibility=current_link.visibility,
            updated_at=min(profile_result.loaded_at, stats_result.loaded_at),
            from_cache=profile_result.from_cache and stats_result.from_cache,
        )

    async def get_achievements(
        self,
        *,
        guild_id: int,
        requester_user_id: int,
        target_user_id: int,
        force_refresh: bool = False,
    ) -> MlbbAchievementsSnapshot:
        link = await self._get_authorized_link(
            guild_id=guild_id,
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
        )
        self._reserve_refresh_if_requested(
            link=link,
            requester_user_id=requester_user_id,
            force_refresh=force_refresh,
        )
        jwt = self._decrypt_credential(link)
        stats_result = await self._cache.get_stats(
            guild_id=guild_id,
            discord_user_id=target_user_id,
            loader=lambda: self._load_stats(link, jwt),
            force_refresh=force_refresh,
        )
        stats = stats_result.value
        current_link = await self._get_authorized_link(
            guild_id=guild_id,
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
        )
        return MlbbAchievementsSnapshot(
            discord_user_id=target_user_id,
            player_name=current_link.player_name,
            avatar_url=current_link.avatar_url,
            longest_win_streak=stats.longest_win_streak,
            game_time_hours=stats.game_time_hours,
            average_score=normalize_score(stats.average_score_raw),
            highlights=tuple(
                MlbbAchievement(
                    kind=highlight.kind.value,
                    value=highlight.value,
                    occurred_at=highlight.occurred_at,
                    hero_name=highlight.hero.name,
                    hero_image_url=(
                        highlight.hero.large_image_url or highlight.hero.image_url
                    ),
                )
                for highlight in stats.highlights
            ),
            visibility=current_link.visibility,
            updated_at=stats_result.loaded_at,
            from_cache=stats_result.from_cache,
        )

    async def set_visibility(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        visibility: MlbbProfileVisibility,
    ) -> MlbbProfileVisibility:
        if visibility not in {
            MlbbProfileVisibility.PRIVATE,
            MlbbProfileVisibility.GUILD,
        }:
            raise MlbbProfileAccessDeniedError(
                "A visibilidade deve ser PRIVATE ou GUILD."
            )
        await self._get_authorized_link(
            guild_id=guild_id,
            requester_user_id=discord_user_id,
            target_user_id=discord_user_id,
        )
        updated = await self._repository.update_visibility(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            visibility=visibility,
            now=self._now(),
        )
        if updated is None:
            raise MlbbProfileNotLinkedError("Vínculo MLBB não encontrado.")
        self._ensure_active(updated)
        if updated.visibility is not visibility:
            raise MlbbProfileProviderRejectedError(
                "A visibilidade MLBB mudou durante a operação."
            )
        self._cache.invalidate_account(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        return updated.visibility

    async def _get_authorized_link(
        self,
        *,
        guild_id: int,
        requester_user_id: int,
        target_user_id: int,
    ) -> MlbbAccountLink:
        self._ensure_enabled()
        _validate_context(guild_id, requester_user_id, target_user_id)
        link = await self._repository.get_link(
            guild_id=guild_id,
            discord_user_id=target_user_id,
        )
        if link is None:
            raise MlbbProfileNotLinkedError("Vínculo MLBB não encontrado.")
        self._ensure_active(link)
        if (
            requester_user_id != target_user_id
            and link.visibility is MlbbProfileVisibility.PRIVATE
        ):
            raise MlbbProfileAccessDeniedError("O perfil MLBB é privado.")
        return link

    async def _load_profile(
        self,
        link: MlbbAccountLink,
        jwt: str,
    ) -> MlbbPlayerProfile:
        profile = await self._provider_call(
            link,
            lambda: self._client.get_user_info(jwt=jwt),
        )
        if profile.role_id != link.role_id or profile.zone_id != link.zone_id:
            self._cache.invalidate_account(
                guild_id=link.guild_id,
                discord_user_id=link.discord_user_id,
            )
            raise MlbbProfileIdentityMismatchError(
                "A API retornou uma conta diferente do vínculo."
            )
        updated = await self._repository.update_profile_metadata(
            guild_id=link.guild_id,
            discord_user_id=link.discord_user_id,
            player_name=profile.name,
            avatar_url=profile.avatar_url,
            country_code=profile.country_code,
            now=self._now(),
        )
        if updated is None:
            raise MlbbProfileNotLinkedError("Vínculo MLBB não encontrado.")
        self._ensure_active(updated)
        return profile

    async def _load_stats(
        self,
        link: MlbbAccountLink,
        jwt: str,
    ) -> MlbbPlayerStatsRaw:
        return await self._provider_call(
            link,
            lambda: self._client.get_user_stats(jwt=jwt),
        )

    async def _provider_call(
        self,
        link: MlbbAccountLink,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        try:
            return await operation()
        except MlbbSessionExpiredError:
            await self._repository.mark_reauth_required(
                guild_id=link.guild_id,
                discord_user_id=link.discord_user_id,
                now=self._now(),
            )
            self._cache.invalidate_account(
                guild_id=link.guild_id,
                discord_user_id=link.discord_user_id,
            )
            raise MlbbProfileReauthenticationRequiredError(
                "A sessão MLBB expirou."
            ) from None
        except MlbbUnavailableError:
            raise MlbbProfileProviderUnavailableError(
                "A API MLBB está temporariamente indisponível."
            ) from None
        except MlbbIntegrationError:
            raise MlbbProfileProviderRejectedError(
                "A API MLBB retornou uma resposta inválida."
            ) from None

    def _decrypt_credential(self, link: MlbbAccountLink) -> str:
        if not link.encrypted_jwt:
            raise MlbbProfileReauthenticationRequiredError(
                "O vínculo MLBB não possui uma sessão ativa."
            )
        try:
            return self._token_cipher.decrypt(link.encrypted_jwt)
        except MlbbTokenCipherError:
            raise MlbbProfileProviderRejectedError(
                "A sessão MLBB armazenada não pôde ser lida."
            ) from None

    def _reserve_refresh_if_requested(
        self,
        *,
        link: MlbbAccountLink,
        requester_user_id: int,
        force_refresh: bool,
    ) -> None:
        if not force_refresh:
            return
        if requester_user_id != link.discord_user_id:
            raise MlbbProfileAccessDeniedError(
                "Somente o dono pode forçar uma atualização."
            )
        try:
            self._cache.reserve_refresh(
                guild_id=link.guild_id,
                discord_user_id=link.discord_user_id,
            )
        except MlbbRefreshCooldownError as exc:
            raise MlbbProfileRefreshCooldownError(exc.retry_after_seconds) from None

    def _ensure_enabled(self) -> None:
        if not self._enabled:
            raise MlbbProfileFeatureDisabledError("A integração MLBB está desativada.")

    @staticmethod
    def _ensure_active(link: MlbbAccountLink) -> None:
        if link.status is MlbbAccountLinkStatus.REAUTH_REQUIRED:
            raise MlbbProfileReauthenticationRequiredError(
                "O vínculo MLBB precisa ser reautenticado."
            )
        if link.status is not MlbbAccountLinkStatus.ACTIVE:
            raise MlbbProfileNotLinkedError("Não há vínculo MLBB ativo.")

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _validate_context(
    guild_id: int,
    requester_user_id: int,
    target_user_id: int,
) -> None:
    if guild_id <= 0 or requester_user_id <= 0 or target_user_id <= 0:
        raise MlbbProfileAccessDeniedError("O contexto da consulta MLBB é inválido.")
