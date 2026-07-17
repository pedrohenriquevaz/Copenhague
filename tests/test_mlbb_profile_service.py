from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet

from app.integrations.mlbb import (
    MlbbHeroSummary,
    MlbbPlayerProfile,
    MlbbPlayerStatsRaw,
    MlbbSessionExpiredError,
    MlbbStatHighlight,
    MlbbStatHighlightKind,
    MlbbTimeoutError,
)
from app.models.mlbb import (
    MlbbAccountLink,
    MlbbAccountLinkStatus,
    MlbbProfileVisibility,
)
from app.services.mlbb_cache_service import MlbbCacheService
from app.services.mlbb_profile_service import (
    MlbbProfileAccessDeniedError,
    MlbbProfileIdentityMismatchError,
    MlbbProfileNotLinkedError,
    MlbbProfileProviderUnavailableError,
    MlbbProfileReauthenticationRequiredError,
    MlbbProfileRefreshCooldownError,
    MlbbProfileService,
)
from app.services.mlbb_token_cipher import MlbbTokenCipher

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
PLAIN_JWT = "jwt-ficticio-super-secreto"


class FakeMlbbProfileRepository:
    def __init__(self, link: MlbbAccountLink) -> None:
        self.link = link
        self.metadata_updates = 0
        self.reauth_updates = 0

    async def get_link(
        self, *, guild_id: int, discord_user_id: int
    ) -> MlbbAccountLink | None:
        if (
            self.link.guild_id == guild_id
            and self.link.discord_user_id == discord_user_id
        ):
            return self.link
        return None

    async def update_profile_metadata(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        player_name: str,
        avatar_url: str | None,
        country_code: str | None,
        now: datetime,
    ) -> MlbbAccountLink | None:
        current = await self.get_link(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        if current is None or current.status is not MlbbAccountLinkStatus.ACTIVE:
            return current
        self.metadata_updates += 1
        self.link = replace(
            current,
            player_name=player_name,
            avatar_url=avatar_url,
            country_code=country_code,
            last_validated_at=now,
            last_used_at=now,
            updated_at=now,
        )
        return self.link

    async def update_visibility(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        visibility: MlbbProfileVisibility,
        now: datetime,
    ) -> MlbbAccountLink | None:
        current = await self.get_link(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        if current is None or current.status is not MlbbAccountLinkStatus.ACTIVE:
            return current
        self.link = replace(current, visibility=visibility, updated_at=now)
        return self.link

    async def mark_reauth_required(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> MlbbAccountLink | None:
        current = await self.get_link(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        if current is None:
            return None
        self.reauth_updates += 1
        if current.status is MlbbAccountLinkStatus.ACTIVE:
            self.link = replace(
                current,
                status=MlbbAccountLinkStatus.REAUTH_REQUIRED,
                updated_at=now,
            )
        return self.link


class FakeMlbbProfileClient:
    def __init__(
        self,
        profile: MlbbPlayerProfile,
        stats: MlbbPlayerStatsRaw,
    ) -> None:
        self.profile = profile
        self.stats = stats
        self.info_calls = 0
        self.stats_calls = 0
        self.info_error: BaseException | None = None
        self.stats_error: BaseException | None = None

    async def get_user_info(self, *, jwt: str) -> MlbbPlayerProfile:
        assert jwt == PLAIN_JWT
        self.info_calls += 1
        if self.info_error is not None:
            raise self.info_error
        return self.profile

    async def get_user_stats(self, *, jwt: str) -> MlbbPlayerStatsRaw:
        assert jwt == PLAIN_JWT
        self.stats_calls += 1
        if self.stats_error is not None:
            raise self.stats_error
        return self.stats


@pytest.fixture
def profile_parts():
    cipher = MlbbTokenCipher((Fernet.generate_key().decode("ascii"),))
    link = MlbbAccountLink(
        guild_id=10,
        discord_user_id=20,
        role_id=123456789,
        zone_id=1234,
        player_name="Nome antigo",
        avatar_url=None,
        country_code=None,
        encrypted_jwt=cipher.encrypt(PLAIN_JWT),
        status=MlbbAccountLinkStatus.ACTIVE,
        visibility=MlbbProfileVisibility.GUILD,
        verified_at=NOW,
        last_validated_at=NOW,
        last_used_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    profile = MlbbPlayerProfile(
        role_id=123456789,
        zone_id=1234,
        name="Jogador Fictício",
        avatar_url="https://cdn.example.test/avatar.png",
        level=77,
        current_rank_code=8000,
        highest_rank_code=9999,
        country_code="BR",
    )
    highlight = MlbbStatHighlight(
        kind=MlbbStatHighlightKind.HIGHEST_KILLS,
        value=24,
        occurred_at=1_700_000_000,
        hero=MlbbHeroSummary(
            hero_id=1,
            name="Herói Teste",
            image_url="https://cdn.example.test/hero.png",
            large_image_url=None,
        ),
        battle_id="90071992547409931234",
        season_id=42,
    )
    stats = MlbbPlayerStatsRaw(
        wins=18,
        matches=30,
        average_score_raw=762.5,
        game_time_hours=12.25,
        mvp_count=7,
        longest_win_streak=4,
        highlights=(highlight,),
        season_ids=(42,),
    )
    repository = FakeMlbbProfileRepository(link)
    client = FakeMlbbProfileClient(profile, stats)
    cache = MlbbCacheService()
    service = MlbbProfileService(
        repository,  # type: ignore[arg-type]
        client,  # type: ignore[arg-type]
        cipher,
        cache,
        enabled=True,
        clock=lambda: NOW,
    )
    return service, repository, client, cache


@pytest.mark.asyncio
async def test_profile_calculates_wr_ranks_and_persists_identity(profile_parts) -> None:
    service, repository, client, _ = profile_parts

    result = await service.get_profile(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
    )

    assert result.win_rate == 60.0
    assert result.matches == 30
    assert result.wins == 18
    assert result.current_rank == "Rank não mapeado (código 8000)"
    assert result.highest_rank == "Rank não mapeado (código 9999)"
    assert repository.link.player_name == "Jogador Fictício"
    assert repository.link.avatar_url == "https://cdn.example.test/avatar.png"
    assert repository.link.last_validated_at == NOW
    assert repository.metadata_updates == 1
    assert client.info_calls == 1
    assert client.stats_calls == 1


@pytest.mark.asyncio
async def test_zero_matches_and_optional_fields_are_safe(profile_parts) -> None:
    service, _, client, _ = profile_parts
    client.profile = replace(
        client.profile,
        avatar_url=None,
        level=None,
        current_rank_code=None,
        highest_rank_code=None,
        country_code=None,
    )
    client.stats = replace(
        client.stats,
        wins=0,
        matches=0,
        average_score_raw=None,
        game_time_hours=None,
        highlights=(),
    )

    result = await service.get_profile(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
    )
    achievements = await service.get_achievements(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
    )

    assert result.win_rate == 0.0
    assert result.level is None
    assert result.current_rank == "Não disponível"
    assert result.country_code is None
    assert achievements.average_score is None
    assert achievements.game_time_hours is None


@pytest.mark.asyncio
async def test_achievements_normalize_score_and_keep_hero(profile_parts) -> None:
    service, _, _, _ = profile_parts

    result = await service.get_achievements(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
    )

    assert result.average_score == 7.62
    assert result.longest_win_streak == 4
    assert result.highlights[0].kind == "HIGHEST_KILLS"
    assert result.highlights[0].hero_name == "Herói Teste"
    assert result.highlights[0].hero_image_url.endswith("/hero.png")


@pytest.mark.asyncio
async def test_profile_cache_hit_avoids_new_provider_calls(profile_parts) -> None:
    service, repository, client, _ = profile_parts

    first = await service.get_profile(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
    )
    second = await service.get_profile(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
    )

    assert first.from_cache is False
    assert second.from_cache is True
    assert client.info_calls == 1
    assert client.stats_calls == 1
    assert repository.metadata_updates == 1


@pytest.mark.asyncio
async def test_private_profile_blocks_third_party_before_provider(
    profile_parts,
) -> None:
    service, repository, client, _ = profile_parts
    repository.link = replace(
        repository.link,
        visibility=MlbbProfileVisibility.PRIVATE,
    )

    with pytest.raises(MlbbProfileAccessDeniedError):
        await service.get_profile(
            guild_id=10,
            requester_user_id=30,
            target_user_id=20,
        )

    assert client.info_calls == 0
    assert client.stats_calls == 0


@pytest.mark.asyncio
async def test_guild_visibility_allows_member_in_same_guild(profile_parts) -> None:
    service, _, _, _ = profile_parts

    access = await service.check_access(
        guild_id=10,
        requester_user_id=30,
        target_user_id=20,
    )

    assert access.is_owner is False
    assert access.visibility is MlbbProfileVisibility.GUILD


@pytest.mark.asyncio
async def test_cross_guild_lookup_is_not_allowed(profile_parts) -> None:
    service, _, _, _ = profile_parts

    with pytest.raises(MlbbProfileNotLinkedError):
        await service.check_access(
            guild_id=99,
            requester_user_id=30,
            target_user_id=20,
        )


@pytest.mark.asyncio
async def test_expired_session_marks_reauth_and_invalidates(profile_parts) -> None:
    service, repository, client, cache = profile_parts
    client.info_error = MlbbSessionExpiredError()

    with pytest.raises(MlbbProfileReauthenticationRequiredError):
        await service.get_profile(
            guild_id=10,
            requester_user_id=20,
            target_user_id=20,
        )

    assert repository.link.status is MlbbAccountLinkStatus.REAUTH_REQUIRED
    assert repository.reauth_updates == 1
    assert cache._entries == {}


@pytest.mark.asyncio
async def test_timeout_preserves_active_link_and_persists_valid_info(
    profile_parts,
) -> None:
    service, repository, client, _ = profile_parts
    client.stats_error = MlbbTimeoutError()

    with pytest.raises(MlbbProfileProviderUnavailableError):
        await service.get_profile(
            guild_id=10,
            requester_user_id=20,
            target_user_id=20,
        )

    assert repository.link.status is MlbbAccountLinkStatus.ACTIVE
    assert repository.reauth_updates == 0
    assert repository.link.player_name == "Jogador Fictício"


@pytest.mark.asyncio
async def test_provider_identity_mismatch_does_not_mark_reauth(profile_parts) -> None:
    service, repository, client, _ = profile_parts
    client.profile = replace(client.profile, role_id=999)

    with pytest.raises(MlbbProfileIdentityMismatchError):
        await service.get_profile(
            guild_id=10,
            requester_user_id=20,
            target_user_id=20,
        )

    assert repository.link.status is MlbbAccountLinkStatus.ACTIVE
    assert repository.metadata_updates == 0


@pytest.mark.asyncio
async def test_unlink_race_does_not_return_loaded_profile(profile_parts) -> None:
    service, repository, client, _ = profile_parts

    async def revoke_during_stats(*, jwt: str) -> MlbbPlayerStatsRaw:
        assert jwt == PLAIN_JWT
        client.stats_calls += 1
        repository.link = replace(
            repository.link,
            status=MlbbAccountLinkStatus.REVOKED,
            encrypted_jwt=None,
        )
        return client.stats

    client.get_user_stats = revoke_during_stats  # type: ignore[method-assign]

    with pytest.raises(MlbbProfileNotLinkedError):
        await service.get_profile(
            guild_id=10,
            requester_user_id=20,
            target_user_id=20,
        )


@pytest.mark.asyncio
async def test_safe_snapshot_and_errors_never_include_credentials(
    profile_parts,
) -> None:
    service, repository, client, _ = profile_parts
    encrypted = repository.link.encrypted_jwt
    result = await service.get_profile(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
    )
    client.info_error = MlbbSessionExpiredError(PLAIN_JWT)

    rendered = repr(result)
    assert PLAIN_JWT not in rendered
    assert encrypted not in rendered
    assert "jwt" not in {field.name for field in result.__dataclass_fields__.values()}


@pytest.mark.asyncio
async def test_visibility_update_invalidates_cache(profile_parts) -> None:
    service, repository, _, cache = profile_parts
    await service.get_profile(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
    )

    result = await service.set_visibility(
        guild_id=10,
        discord_user_id=20,
        visibility=MlbbProfileVisibility.PRIVATE,
    )

    assert result is MlbbProfileVisibility.PRIVATE
    assert repository.link.visibility is MlbbProfileVisibility.PRIVATE
    assert cache._entries == {}


@pytest.mark.asyncio
async def test_manual_refresh_respects_cooldown(profile_parts) -> None:
    service, _, _, _ = profile_parts
    await service.get_profile(
        guild_id=10,
        requester_user_id=20,
        target_user_id=20,
        force_refresh=True,
    )

    with pytest.raises(MlbbProfileRefreshCooldownError):
        await service.get_profile(
            guild_id=10,
            requester_user_id=20,
            target_user_id=20,
            force_refresh=True,
        )
