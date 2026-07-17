from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar, cast

T = TypeVar("T")


class MlbbCacheResource(StrEnum):
    PROFILE = "profile"
    STATS = "stats"


@dataclass(frozen=True, slots=True)
class MlbbCacheKey:
    """Identificador seguro do cache; credenciais nunca fazem parte da chave."""

    resource: MlbbCacheResource
    guild_id: int
    discord_user_id: int


@dataclass(frozen=True, slots=True)
class MlbbCachedResult(Generic[T]):
    value: T
    loaded_at: datetime
    from_cache: bool

    @property
    def cached_at(self) -> datetime:
        """Alias legivel para consumidores que exibem a data da atualizacao."""

        return self.loaded_at


class MlbbRefreshCooldownError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Aguarde antes de atualizar os dados MLBB novamente.")
        self.retry_after_seconds = retry_after_seconds

    @property
    def retry_after(self) -> int:
        return self.retry_after_seconds


@dataclass(frozen=True, slots=True)
class _AccountKey:
    guild_id: int
    discord_user_id: int


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    loaded_at: datetime
    expires_at: float


@dataclass(slots=True)
class _LockRecord:
    lock: asyncio.Lock
    ref_count: int = 0


class MlbbCacheService:
    """Cache local com TTL, deduplicacao e invalidacao por conta.

    O cache nao implementa fallback stale. Excecoes do loader sempre chegam ao
    chamador e entradas expiradas nunca sao devolvidas.
    """

    def __init__(
        self,
        *,
        profile_ttl_seconds: float = 300,
        stats_ttl_seconds: float = 120,
        refresh_cooldown_seconds: float = 30,
        monotonic_clock: Callable[[], float] | None = None,
        utc_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if profile_ttl_seconds <= 0:
            raise ValueError("profile_ttl_seconds precisa ser positivo.")
        if stats_ttl_seconds <= 0:
            raise ValueError("stats_ttl_seconds precisa ser positivo.")
        if refresh_cooldown_seconds <= 0:
            raise ValueError("refresh_cooldown_seconds precisa ser positivo.")

        self._ttls = {
            MlbbCacheResource.PROFILE: float(profile_ttl_seconds),
            MlbbCacheResource.STATS: float(stats_ttl_seconds),
        }
        self._refresh_cooldown_seconds = float(refresh_cooldown_seconds)
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._utc_clock = utc_clock or (lambda: datetime.now(UTC))
        self._entries: dict[MlbbCacheKey, _CacheEntry] = {}
        self._locks: dict[MlbbCacheKey, _LockRecord] = {}
        self._account_generations: dict[_AccountKey, int] = {}
        self._refresh_reservations: dict[_AccountKey, float] = {}

    async def get_profile(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        loader: Callable[[], Awaitable[T]],
        force_refresh: bool = False,
    ) -> MlbbCachedResult[T]:
        return await self.get_or_load(
            resource=MlbbCacheResource.PROFILE,
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            loader=loader,
            force_refresh=force_refresh,
        )

    async def get_stats(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        loader: Callable[[], Awaitable[T]],
        force_refresh: bool = False,
    ) -> MlbbCachedResult[T]:
        return await self.get_or_load(
            resource=MlbbCacheResource.STATS,
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            loader=loader,
            force_refresh=force_refresh,
        )

    async def get_or_load(
        self,
        *,
        resource: MlbbCacheResource | str,
        guild_id: int,
        discord_user_id: int,
        loader: Callable[[], Awaitable[T]],
        force_refresh: bool = False,
        ttl_seconds: float | None = None,
    ) -> MlbbCachedResult[T]:
        normalized_resource = MlbbCacheResource(resource)
        key = MlbbCacheKey(normalized_resource, guild_id, discord_user_id)
        ttl = self._ttls[normalized_resource] if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            raise ValueError("ttl_seconds precisa ser positivo.")

        observed_entry = self._valid_entry(key)
        if observed_entry is not None and not force_refresh:
            return self._result(observed_entry, from_cache=True)

        lock_record = self._retain_lock(key)
        try:
            async with lock_record.lock:
                current_entry = self._valid_entry(key)
                if current_entry is not None and (
                    not force_refresh or current_entry is not observed_entry
                ):
                    return self._result(current_entry, from_cache=True)

                account_key = _AccountKey(guild_id, discord_user_id)
                generation = self._account_generations.get(account_key, 0)
                value = await loader()
                loaded_at = self._now_utc()
                entry = _CacheEntry(
                    value=value,
                    loaded_at=loaded_at,
                    expires_at=self._monotonic_clock() + float(ttl),
                )
                if generation == self._account_generations.get(account_key, 0):
                    self._entries[key] = entry
                return self._result(entry, from_cache=False)
        finally:
            self._release_lock(key, lock_record)

    def reserve_refresh(self, *, guild_id: int, discord_user_id: int) -> None:
        """Reserva o cooldown de uma atualizacao solicitada manualmente."""

        account_key = _AccountKey(guild_id, discord_user_id)
        now = self._monotonic_clock()
        available_at = self._refresh_reservations.get(account_key)
        if available_at is not None and available_at > now:
            raise MlbbRefreshCooldownError(max(1, math.ceil(available_at - now)))
        self._refresh_reservations[account_key] = now + self._refresh_cooldown_seconds

    def invalidate_account(self, *, guild_id: int, discord_user_id: int) -> None:
        """Invalida perfil, stats e cooldown, inclusive loads ainda em voo."""

        account_key = _AccountKey(guild_id, discord_user_id)
        self._account_generations[account_key] = (
            self._account_generations.get(account_key, 0) + 1
        )
        self._refresh_reservations.pop(account_key, None)
        for resource in MlbbCacheResource:
            self._entries.pop(MlbbCacheKey(resource, guild_id, discord_user_id), None)

    @property
    def active_lock_count(self) -> int:
        """Quantidade de registros de lock retidos por operacoes em andamento."""

        return len(self._locks)

    def _valid_entry(self, key: MlbbCacheKey) -> _CacheEntry | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._monotonic_clock():
            self._entries.pop(key, None)
            return None
        return entry

    def _retain_lock(self, key: MlbbCacheKey) -> _LockRecord:
        record = self._locks.get(key)
        if record is None:
            record = _LockRecord(asyncio.Lock())
            self._locks[key] = record
        record.ref_count += 1
        return record

    def _release_lock(self, key: MlbbCacheKey, record: _LockRecord) -> None:
        record.ref_count -= 1
        if record.ref_count == 0 and not record.lock.locked():
            if self._locks.get(key) is record:
                self._locks.pop(key, None)

    def _now_utc(self) -> datetime:
        value = self._utc_clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _result(entry: _CacheEntry, *, from_cache: bool) -> MlbbCachedResult[T]:
        return MlbbCachedResult(
            value=cast(T, entry.value),
            loaded_at=entry.loaded_at,
            from_cache=from_cache,
        )
