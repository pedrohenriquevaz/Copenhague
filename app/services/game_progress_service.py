from __future__ import annotations

from dataclasses import replace

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
    """Erro de validação do progresso de jogos."""


MAX_ACHIEVEMENT_REWARD_POINTS = 100_000


def _achievement(
    achievement_key: str,
    name: str,
    description: str,
    reward_points: int,
    badge_emoji: str,
) -> GameAchievement:
    return GameAchievement(
        guild_id=0,
        achievement_key=achievement_key,
        name=name,
        description=description,
        reward_points=reward_points,
        badge_emoji=badge_emoji,
        is_active=True,
        created_at=utc_now(),
    )


DEFAULT_ACHIEVEMENTS: tuple[GameAchievement, ...] = (
    _achievement(
        "first_bet",
        "Primeira aposta",
        "Fez sua primeira aposta nos jogos do servidor.",
        25,
        "🎟️",
    ),
    _achievement(
        "first_win",
        "Primeira vitória",
        "Venceu pela primeira vez em um jogo.",
        25,
        "🏆",
    ),
    _achievement(
        "first_loss",
        "Primeira derrota",
        "Jogou, perdeu e continuou na esportiva.",
        25,
        "🧭",
    ),
    _achievement(
        "first_scratch",
        "Primeira raspadinha",
        "Comprou sua primeira raspadinha.",
        25,
        "🎫",
    ),
    _achievement(
        "first_coin_flip",
        "Cara ou coroa",
        "Jogou sua primeira partida de cara ou coroa.",
        25,
        "🪙",
    ),
    _achievement(
        "first_dice",
        "Primeiro lançamento",
        "Jogou dados pela primeira vez.",
        25,
        "🎲",
    ),
    _achievement(
        "first_slot",
        "Primeiro giro",
        "Girou a slot machine pela primeira vez.",
        25,
        "🎰",
    ),
    _achievement(
        "first_roulette",
        "Primeira roleta",
        "Apostou na roleta pela primeira vez.",
        25,
        "🔴",
    ),
    _achievement(
        "first_mascot_race",
        "Primeira corrida solo",
        "Apostou em uma corrida de mascotes individual.",
        25,
        "🏁",
    ),
    _achievement(
        "first_duel",
        "Primeiro X1",
        "Participou de seu primeiro duelo.",
        25,
        "⚔️",
    ),
    _achievement(
        "first_blackjack",
        "Primeiro BlackJack",
        "Entrou em sua primeira mesa de BlackJack.",
        25,
        "🃏",
    ),
    _achievement(
        "scratch_win",
        "Raspadinha premiada",
        "Ganhou pontos em uma raspadinha.",
        50,
        "✨",
    ),
    _achievement(
        "duel_win",
        "Vitória no X1",
        "Venceu um duelo contra outro membro.",
        50,
        "🥇",
    ),
    _achievement(
        "collective_race_win",
        "Venceu corrida coletiva",
        "Acertou o mascote vencedor de uma corrida coletiva.",
        50,
        "🏁",
    ),
    _achievement(
        "games_10",
        "Aquecimento da banca",
        "Fez 10 apostas em jogos do servidor.",
        50,
        "📌",
    ),
    _achievement(
        "wins_5",
        "Cinco vitórias",
        "Somou 5 vitórias em jogos do servidor.",
        50,
        "✅",
    ),
    _achievement(
        "points_10k",
        "Primeiros 10 mil",
        "Acumulou 10.000 pontos ganhos no servidor.",
        100,
        "💰",
    ),
    _achievement(
        "games_50",
        "Presença constante",
        "Fez 50 apostas em jogos do servidor.",
        100,
        "📊",
    ),
    _achievement(
        "wins_25",
        "Sequência respeitável",
        "Somou 25 vitórias em jogos do servidor.",
        100,
        "🌟",
    ),
    _achievement(
        "wager_10k",
        "10 mil na mesa",
        "Apostou 10.000 pontos no total.",
        100,
        "💸",
    ),
    _achievement(
        "big_win_1k",
        "Prêmio de 1 mil",
        "Recebeu pelo menos 1.000 pontos em uma única aposta.",
        100,
        "🎯",
    ),
    _achievement(
        "points_50k",
        "Carteira pesada",
        "Acumulou 50.000 pontos ganhos no servidor.",
        300,
        "💼",
    ),
    _achievement(
        "wager_50k",
        "50 mil em apostas",
        "Apostou 50.000 pontos no total.",
        300,
        "🏦",
    ),
    _achievement(
        "profit_10k",
        "Lucro de 10 mil",
        "Ficou com 10.000 pontos de lucro líquido nos jogos.",
        300,
        "📈",
    ),
    _achievement(
        "big_win_5k",
        "Tacada de 5 mil",
        "Recebeu pelo menos 5.000 pontos em uma única aposta.",
        300,
        "💎",
    ),
    _achievement(
        "blackjack_streak_3",
        "Mesa quente",
        "Venceu 3 partidas seguidas de BlackJack.",
        300,
        "🔥",
    ),
    _achievement(
        "scratch_veteran",
        "Veterano da raspadinha",
        "Comprou 25 raspadinhas.",
        300,
        "🎫",
    ),
    _achievement(
        "duel_king",
        "Rei do X1",
        "Venceu 10 duelos contra membros da comunidade.",
        500,
        "👑",
    ),
    _achievement(
        "collective_race_king",
        "Domador das corridas",
        "Venceu 10 corridas coletivas.",
        500,
        "🐾",
    ),
    _achievement(
        "scratch_jackpot",
        "Jackpot da raspadinha",
        "Encontrou o prêmio acumulado da raspadinha.",
        750,
        "💎",
    ),
)

DEFAULT_ACHIEVEMENT_BY_KEY = {
    achievement.achievement_key: achievement for achievement in DEFAULT_ACHIEVEMENTS
}

MILESTONE_ACHIEVEMENTS = (
    ("games_10", lambda summary: summary.total_games_played >= 10),
    ("games_50", lambda summary: summary.total_games_played >= 50),
    ("wins_5", lambda summary: summary.total_wins >= 5),
    ("wins_25", lambda summary: summary.total_wins >= 25),
    ("points_10k", lambda summary: summary.wallet.total_earned >= 10_000),
    ("points_50k", lambda summary: summary.wallet.total_earned >= 50_000),
    ("wager_10k", lambda summary: summary.total_wagered >= 10_000),
    ("wager_50k", lambda summary: summary.total_wagered >= 50_000),
    ("profit_10k", lambda summary: summary.net_profit >= 10_000),
    ("big_win_1k", lambda summary: summary.biggest_win >= 1_000),
    ("big_win_5k", lambda summary: summary.biggest_win >= 5_000),
    ("blackjack_streak_3", lambda summary: summary.blackjack_best_streak >= 3),
    ("scratch_veteran", lambda summary: summary.scratch_plays >= 25),
    ("duel_king", lambda summary: summary.duel_wins >= 10),
    ("collective_race_king", lambda summary: summary.collective_race_wins >= 10),
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

    async def configure_achievement_reward(
        self,
        guild_id: int,
        achievement_key: str,
        reward_points: int,
    ) -> GameAchievement:
        normalized_key = achievement_key.strip()
        if normalized_key not in DEFAULT_ACHIEVEMENT_BY_KEY:
            raise GameProgressValidationError("Conquista não encontrada.")
        if reward_points < 0:
            raise GameProgressValidationError("A recompensa não pode ser negativa.")
        if reward_points > MAX_ACHIEVEMENT_REWARD_POINTS:
            raise GameProgressValidationError(
                f"A recompensa máxima é {MAX_ACHIEVEMENT_REWARD_POINTS} pontos."
            )

        await self.ensure_default_achievements(guild_id)
        achievement = await self._repository.update_achievement_reward(
            guild_id,
            normalized_key,
            reward_points,
        )
        if achievement is None:
            raise GameProgressValidationError("Conquista não encontrada.")
        return achievement

    async def unlock(
        self,
        guild_id: int,
        user_id: int,
        achievement_key: str,
    ) -> UserGameAchievement | None:
        return await self._unlock(
            guild_id,
            user_id,
            achievement_key,
            ensure_defaults=True,
        )

    async def _unlock(
        self,
        guild_id: int,
        user_id: int,
        achievement_key: str,
        *,
        ensure_defaults: bool,
    ) -> UserGameAchievement | None:
        if ensure_defaults:
            await self.ensure_default_achievements(guild_id)
        unlocked, is_new = await self._repository.unlock_achievement(
            guild_id,
            user_id,
            achievement_key,
        )
        if not is_new or unlocked is None:
            return None

        reward_points = unlocked.achievement.reward_points
        await self._grant_achievement_reward_once(
            guild_id,
            user_id,
            achievement_key,
            reward_points,
        )
        return unlocked

    async def list_user_achievements(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UserGameAchievement]:
        await self.evaluate_user_milestones(guild_id, user_id)
        achievements = await self._repository.list_user_achievements(guild_id, user_id)
        await self._grant_unpaid_achievement_rewards(guild_id, user_id, achievements)
        return achievements

    async def evaluate_user_milestones(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UserGameAchievement]:
        await self.ensure_default_achievements(guild_id)
        summary = await self._economy_repository.get_user_game_progress_summary(
            guild_id,
            user_id,
        )
        unlocked: list[UserGameAchievement] = []
        for achievement_key, condition in MILESTONE_ACHIEVEMENTS:
            if not condition(summary):
                continue
            achievement = await self._unlock(
                guild_id,
                user_id,
                achievement_key,
                ensure_defaults=False,
            )
            if achievement is not None:
                unlocked.append(achievement)
        return unlocked

    async def _grant_unpaid_achievement_rewards(
        self,
        guild_id: int,
        user_id: int,
        achievements: list[UserGameAchievement],
    ) -> None:
        for item in achievements:
            await self._grant_achievement_reward_once(
                guild_id,
                user_id,
                item.achievement.achievement_key,
                item.achievement.reward_points,
            )

    async def _grant_achievement_reward_once(
        self,
        guild_id: int,
        user_id: int,
        achievement_key: str,
        reward_points: int,
    ) -> None:
        if reward_points <= 0:
            return
        await self._economy_repository.grant_achievement_reward_once(
            guild_id=guild_id,
            user_id=user_id,
            achievement_key=achievement_key,
            amount=reward_points,
        )

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
            raise GameProgressValidationError("Tema sazonal inválido.") from exc
        return await self._repository.set_seasonal_theme(guild_id, parsed_theme)
