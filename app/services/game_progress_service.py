from __future__ import annotations

from dataclasses import replace

from app.models.economy import EconomyTransactionType
from app.models.game_progress import (
    GameAchievement,
    JackpotState,
    SeasonalSetting,
    SeasonalTheme,
    UserGameAchievement,
)
from app.models.giveaway import utc_now
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.repositories.game_progress_repository import GameProgressRepositoryProtocol


class GameProgressServiceError(Exception):
    """Erro base do progresso de jogos."""


class GameProgressValidationError(GameProgressServiceError):
    """Erro de validacao do progresso de jogos."""


DEFAULT_ACHIEVEMENTS: tuple[GameAchievement, ...] = (
    GameAchievement(
        guild_id=0,
        achievement_key="first_bet",
        name="Primeira aposta",
        description="Fez sua primeira aposta nos jogos do servidor.",
        reward_points=0,
        badge_emoji="🎟️",
        is_active=True,
        created_at=utc_now(),
    ),
    GameAchievement(
        guild_id=0,
        achievement_key="first_win",
        name="Primeira vitoria",
        description="Venceu pela primeira vez em um jogo.",
        reward_points=0,
        badge_emoji="🏆",
        is_active=True,
        created_at=utc_now(),
    ),
    GameAchievement(
        guild_id=0,
        achievement_key="first_loss",
        name="Primeira derrota",
        description="Jogou, perdeu e continuou na esportiva.",
        reward_points=0,
        badge_emoji="🧭",
        is_active=True,
        created_at=utc_now(),
    ),
    GameAchievement(
        guild_id=0,
        achievement_key="first_scratch",
        name="Primeira raspadinha",
        description="Comprou sua primeira raspadinha.",
        reward_points=0,
        badge_emoji="🎫",
        is_active=True,
        created_at=utc_now(),
    ),
    GameAchievement(
        guild_id=0,
        achievement_key="scratch_jackpot",
        name="Jackpot da raspadinha",
        description="Encontrou o premio acumulado da raspadinha.",
        reward_points=0,
        badge_emoji="💎",
        is_active=True,
        created_at=utc_now(),
    ),
    GameAchievement(
        guild_id=0,
        achievement_key="collective_race_win",
        name="Venceu corrida coletiva",
        description="Acertou o mascote vencedor de uma corrida coletiva.",
        reward_points=0,
        badge_emoji="🏁",
        is_active=True,
        created_at=utc_now(),
    ),
)


class GameProgressService:
    """Conquistas, temas sazonais e jackpots dos jogos."""

    SCRATCH_JACKPOT_KEY = "scratch_card"
    SCRATCH_JACKPOT_CAP = 250_000

    def __init__(
        self,
        repository: GameProgressRepositoryProtocol,
        economy_repository: SQLiteEconomyRepository,
    ) -> None:
        self._repository = repository
        self._economy_repository = economy_repository

    async def ensure_default_achievements(self, guild_id: int) -> None:
        for achievement in DEFAULT_ACHIEVEMENTS:
            await self._repository.ensure_achievement(
                replace(achievement, guild_id=guild_id, created_at=utc_now())
            )

    async def unlock(
        self,
        guild_id: int,
        user_id: int,
        achievement_key: str,
    ) -> UserGameAchievement | None:
        await self.ensure_default_achievements(guild_id)
        unlocked, is_new = await self._repository.unlock_achievement(
            guild_id,
            user_id,
            achievement_key,
        )
        if not is_new or unlocked is None:
            return None

        reward_points = unlocked.achievement.reward_points
        if reward_points > 0:
            await self._economy_repository.mutate_balance(
                guild_id=guild_id,
                user_id=user_id,
                amount=reward_points,
                transaction_type=EconomyTransactionType.SYSTEM_ADJUSTMENT,
                actor_id=None,
                reason="achievement_reward",
                metadata={"achievement_key": achievement_key},
            )
        return unlocked

    async def list_user_achievements(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UserGameAchievement]:
        await self.ensure_default_achievements(guild_id)
        return await self._repository.list_user_achievements(guild_id, user_id)

    async def get_scratch_jackpot(self, guild_id: int) -> JackpotState:
        return await self._repository.get_jackpot(guild_id, self.SCRATCH_JACKPOT_KEY)

    async def add_scratch_jackpot(
        self,
        guild_id: int,
        amount: int,
    ) -> JackpotState:
        if amount <= 0:
            return await self.get_scratch_jackpot(guild_id)
        return await self._repository.add_jackpot(
            guild_id,
            self.SCRATCH_JACKPOT_KEY,
            amount,
            cap=self.SCRATCH_JACKPOT_CAP,
        )

    async def claim_scratch_jackpot(self, guild_id: int) -> JackpotState:
        return await self._repository.claim_jackpot(
            guild_id,
            self.SCRATCH_JACKPOT_KEY,
        )

    async def get_seasonal_theme(self, guild_id: int) -> SeasonalSetting:
        return await self._repository.get_seasonal_theme(guild_id)

    async def set_seasonal_theme(
        self,
        guild_id: int,
        theme: str,
    ) -> SeasonalSetting:
        try:
            parsed_theme = SeasonalTheme(theme.strip().lower())
        except ValueError as exc:
            raise GameProgressValidationError("Tema sazonal invalido.") from exc
        return await self._repository.set_seasonal_theme(guild_id, parsed_theme)
