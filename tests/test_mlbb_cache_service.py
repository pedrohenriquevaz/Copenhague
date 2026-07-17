from __future__ import annotations

import asyncio
from dataclasses import fields
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.services.mlbb_cache_service import (
    MlbbCacheKey,
    MlbbCacheResource,
    MlbbCacheService,
    MlbbRefreshCooldownError,
)


class MutableClocks:
    def __init__(self) -> None:
        self.monotonic_value = 100.0
        self.utc_value = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.monotonic_value

    def utc(self) -> datetime:
        return self.utc_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.utc_value += timedelta(seconds=seconds)


def make_cache(
    clocks: MutableClocks,
    *,
    profile_ttl: float = 300,
    stats_ttl: float = 120,
    cooldown: float = 30,
) -> MlbbCacheService:
    return MlbbCacheService(
        profile_ttl_seconds=profile_ttl,
        stats_ttl_seconds=stats_ttl,
        refresh_cooldown_seconds=cooldown,
        monotonic_clock=clocks.monotonic,
        utc_clock=clocks.utc,
    )


@pytest.mark.asyncio
async def test_profile_cache_miss_then_hit() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks)
    calls = 0

    async def load() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"name": "Jogador ficticio"}

    first = await cache.get_profile(guild_id=10, discord_user_id=20, loader=load)
    clocks.advance(10)
    second = await cache.get_profile(guild_id=10, discord_user_id=20, loader=load)

    assert calls == 1
    assert first.value == {"name": "Jogador ficticio"}
    assert first.from_cache is False
    assert second.from_cache is True
    assert second.loaded_at == first.loaded_at
    assert second.cached_at == first.loaded_at
    assert cache.active_lock_count == 0


@pytest.mark.asyncio
async def test_resources_use_independent_ttls_and_keys() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks, profile_ttl=10, stats_ttl=2)
    profile_calls = 0
    stats_calls = 0

    async def load_profile() -> str:
        nonlocal profile_calls
        profile_calls += 1
        return f"profile-{profile_calls}"

    async def load_stats() -> str:
        nonlocal stats_calls
        stats_calls += 1
        return f"stats-{stats_calls}"

    await cache.get_profile(guild_id=1, discord_user_id=2, loader=load_profile)
    await cache.get_stats(guild_id=1, discord_user_id=2, loader=load_stats)
    clocks.advance(3)

    profile = await cache.get_profile(
        guild_id=1, discord_user_id=2, loader=load_profile
    )
    stats = await cache.get_stats(guild_id=1, discord_user_id=2, loader=load_stats)

    assert profile.value == "profile-1"
    assert profile.from_cache is True
    assert stats.value == "stats-2"
    assert stats.from_cache is False
    assert profile_calls == 1
    assert stats_calls == 2


@pytest.mark.asyncio
async def test_concurrent_misses_are_deduplicated() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def load() -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "profile"

    tasks = [
        asyncio.create_task(
            cache.get_profile(guild_id=1, discord_user_id=2, loader=load)
        )
        for _ in range(8)
    ]
    await started.wait()
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)

    assert calls == 1
    assert sum(not result.from_cache for result in results) == 1
    assert {result.value for result in results} == {"profile"}
    assert cache.active_lock_count == 0


@pytest.mark.asyncio
async def test_force_refresh_reloads_and_concurrent_refreshes_deduplicate() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def initial_load() -> str:
        nonlocal calls
        calls += 1
        return "old"

    async def refresh() -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "new"

    await cache.get_profile(guild_id=1, discord_user_id=2, loader=initial_load)
    tasks = [
        asyncio.create_task(
            cache.get_profile(
                guild_id=1,
                discord_user_id=2,
                loader=refresh,
                force_refresh=True,
            )
        )
        for _ in range(5)
    ]
    await started.wait()
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)

    assert calls == 2
    assert sum(not result.from_cache for result in results) == 1
    assert {result.value for result in results} == {"new"}


def test_manual_refresh_cooldown_is_typed_and_uses_monotonic_time() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks, cooldown=30)

    cache.reserve_refresh(guild_id=1, discord_user_id=2)
    clocks.advance(10.2)
    with pytest.raises(MlbbRefreshCooldownError) as captured:
        cache.reserve_refresh(guild_id=1, discord_user_id=2)

    assert captured.value.retry_after_seconds == 20
    assert captured.value.retry_after == 20

    clocks.advance(19.8)
    cache.reserve_refresh(guild_id=1, discord_user_id=2)


@pytest.mark.asyncio
async def test_invalidate_clears_both_resources_and_refresh_cooldown() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks)
    calls = {"profile": 0, "stats": 0}

    async def load_profile() -> int:
        calls["profile"] += 1
        return calls["profile"]

    async def load_stats() -> int:
        calls["stats"] += 1
        return calls["stats"]

    await cache.get_profile(guild_id=1, discord_user_id=2, loader=load_profile)
    await cache.get_stats(guild_id=1, discord_user_id=2, loader=load_stats)
    cache.reserve_refresh(guild_id=1, discord_user_id=2)
    cache.invalidate_account(guild_id=1, discord_user_id=2)

    cache.reserve_refresh(guild_id=1, discord_user_id=2)
    profile = await cache.get_profile(
        guild_id=1, discord_user_id=2, loader=load_profile
    )
    stats = await cache.get_stats(guild_id=1, discord_user_id=2, loader=load_stats)

    assert profile.value == 2
    assert stats.value == 2
    assert profile.from_cache is False
    assert stats.from_cache is False


@pytest.mark.asyncio
async def test_invalidation_during_load_does_not_repopulate_cache() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def slow_load() -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "invalidated-result"

    task = asyncio.create_task(
        cache.get_profile(guild_id=1, discord_user_id=2, loader=slow_load)
    )
    await started.wait()
    cache.invalidate_account(guild_id=1, discord_user_id=2)
    release.set()

    first = await task

    async def fresh_load() -> str:
        nonlocal calls
        calls += 1
        return "fresh-result"

    second = await cache.get_profile(guild_id=1, discord_user_id=2, loader=fresh_load)
    third = await cache.get_profile(guild_id=1, discord_user_id=2, loader=fresh_load)

    assert first.value == "invalidated-result"
    assert second.value == "fresh-result"
    assert second.from_cache is False
    assert third.from_cache is True
    assert calls == 2


@pytest.mark.asyncio
async def test_expired_value_is_not_used_as_stale_fallback() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks, profile_ttl=1)

    async def load_old() -> str:
        return "old"

    await cache.get_profile(guild_id=1, discord_user_id=2, loader=load_old)
    clocks.advance(2)

    async def fail() -> str:
        raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await cache.get_profile(guild_id=1, discord_user_id=2, loader=fail)

    assert cache.active_lock_count == 0


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_leak_lock_registry_reference() -> None:
    clocks = MutableClocks()
    cache = make_cache(clocks)
    started = asyncio.Event()
    release = asyncio.Event()

    async def load() -> str:
        started.set()
        await release.wait()
        return "value"

    owner = asyncio.create_task(
        cache.get_profile(guild_id=1, discord_user_id=2, loader=load)
    )
    await started.wait()
    waiter = asyncio.create_task(
        cache.get_profile(guild_id=1, discord_user_id=2, loader=load)
    )
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert cache.active_lock_count == 1
    release.set()
    await owner
    assert cache.active_lock_count == 0


@pytest.mark.asyncio
async def test_loaded_at_is_normalized_to_utc() -> None:
    clocks = MutableClocks()
    clocks.utc_value = datetime(2026, 7, 16, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
    cache = make_cache(clocks)

    async def load() -> str:
        return "value"

    result = await cache.get_stats(guild_id=1, discord_user_id=2, loader=load)

    assert result.loaded_at == datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def test_cache_key_cannot_contain_credentials() -> None:
    assert [field.name for field in fields(MlbbCacheKey)] == [
        "resource",
        "guild_id",
        "discord_user_id",
    ]
    key = MlbbCacheKey(MlbbCacheResource.PROFILE, 1, 2)
    assert "jwt" not in repr(key).lower()


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("profile_ttl_seconds", 0),
        ("stats_ttl_seconds", -1),
        ("refresh_cooldown_seconds", 0),
    ],
)
def test_rejects_non_positive_configuration(argument: str, value: int) -> None:
    with pytest.raises(ValueError):
        MlbbCacheService(**{argument: value})
