from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence

from app.models.economy import EconomyTransactionType, UserWallet
from app.models.game_progress import (
    ScratchCardResult,
    ScratchCardTier,
    ScratchCardTierConfig,
    SeasonalTheme,
)
from app.models.guild_settings import GuildEconomySettings
from app.repositories.economy_protocol import EconomyRepositoryProtocol
from app.services.economy_limits import (
    PROFIT_DIFFICULTY_ROLL_MAX,
    apply_daily_casino_profit_cap,
    apply_daily_profit_difficulty_to_probability,
    calculate_daily_profit_difficulty_bps,
    current_daily_profit_window_start,
)
from app.services.game_progress_service import GameProgressService


class ScratchCardServiceError(Exception):
    """Erro base da raspadinha."""


class ScratchCardValidationError(ScratchCardServiceError):
    """Erro de validacao da raspadinha."""


SCRATCH_CARD_TIERS: dict[ScratchCardTier, ScratchCardTierConfig] = {
    ScratchCardTier.BRONZE: ScratchCardTierConfig(
        ScratchCardTier.BRONZE,
        "Bronze",
        50,
        3,
    ),
    ScratchCardTier.PRATA: ScratchCardTierConfig(
        ScratchCardTier.PRATA,
        "Prata",
        100,
        4,
    ),
    ScratchCardTier.OURO: ScratchCardTierConfig(
        ScratchCardTier.OURO,
        "Ouro",
        250,
        5,
    ),
    ScratchCardTier.DIAMANTE: ScratchCardTierConfig(
        ScratchCardTier.DIAMANTE,
        "Diamante",
        500,
        8,
    ),
}

SCRATCH_SYMBOLS: dict[SeasonalTheme, tuple[str, ...]] = {
    SeasonalTheme.NONE: ("🍒", "⭐", "💎", "🔔", "🍀", "7️⃣"),
    SeasonalTheme.NATAL: ("🎄", "🎁", "⭐", "🔔", "❄️", "🍪"),
    SeasonalTheme.HALLOWEEN: ("🎃", "👻", "🦇", "🍬", "🌙", "🕯️"),
    SeasonalTheme.COPA: ("⚽", "🏆", "🥅", "🎽", "⭐", "📣"),
    SeasonalTheme.ANIME: ("🌸", "⭐", "🍜", "🎴", "💎", "🌀"),
    SeasonalTheme.ANIVERSARIO: ("🎂", "🎁", "🎈", "⭐", "🎉", "💎"),
}
JACKPOT_SYMBOL = "💎"

SCRATCH_WIN_GATE_BPS: dict[ScratchCardTier, int] = {
    ScratchCardTier.BRONZE: 10_000,
    ScratchCardTier.PRATA: 8_000,
    ScratchCardTier.OURO: 5_500,
    ScratchCardTier.DIAMANTE: 3_500,
}

SCRATCH_MAX_WINNING_LINES: dict[ScratchCardTier, int] = {
    ScratchCardTier.BRONZE: 3,
    ScratchCardTier.PRATA: 2,
    ScratchCardTier.OURO: 2,
    ScratchCardTier.DIAMANTE: 2,
}
SCRATCH_DAILY_PURCHASE_LIMIT = 10


class ScratchCardService:
    """Jogo de raspadinha 3x3 com jackpot acumulado."""

    def __init__(
        self,
        economy_repository: EconomyRepositoryProtocol,
        progress_service: GameProgressService,
        *,
        rng: random.Random | random.SystemRandom | None = None,
    ) -> None:
        self._economy_repository = economy_repository
        self._progress_service = progress_service
        self._rng = rng or random.SystemRandom()
        self._lock = asyncio.Lock()

    async def play(
        self,
        *,
        guild_id: int,
        user_id: int,
        tier: str,
    ) -> ScratchCardResult:
        config = self._parse_tier(tier)
        settings = await self._economy_repository.get_guild_settings(guild_id)
        if config.cost > settings.casino_max_bet:
            raise ScratchCardValidationError(
                f"A aposta maxima e {settings.casino_max_bet}."
            )
        if config.cost < settings.casino_min_bet_scratch_card:
            raise ScratchCardValidationError(
                "A aposta minima da raspadinha e "
                f"{settings.casino_min_bet_scratch_card}."
            )
        await self._validate_daily_profit_limit(guild_id, user_id)
        difficulty_bps = await self._daily_profit_difficulty_bps(
            settings,
            guild_id,
            user_id,
        )
        seasonal = await self._progress_service.get_seasonal_theme(guild_id)

        async with self._lock:
            if settings.casino_limiters_enabled:
                await self._validate_daily_purchase_limit(guild_id, user_id)
            try:
                debit = await self._economy_repository.mutate_balance(
                    guild_id=guild_id,
                    user_id=user_id,
                    amount=-config.cost,
                    transaction_type=EconomyTransactionType.CASINO_BET,
                    actor_id=None,
                    reason="scratch_card_bet",
                    metadata={"game": "scratch_card", "tier": config.tier.value},
                )
            except ValueError as exc:
                raise ScratchCardValidationError(
                    "Saldo insuficiente para comprar essa raspadinha."
                ) from exc

            await self._progress_service.add_scratch_jackpot(
                guild_id,
                max(1, config.cost // 10),
            )
            grid = self._build_grid(
                seasonal.theme,
                config,
                difficulty_bps=difficulty_bps,
            )
            winning_lines = self._find_winning_lines(grid)
            base_payout = (
                config.cost * config.line_multiplier * len(winning_lines)
                if winning_lines
                else 0
            )
            jackpot_won = await self._resolve_jackpot(guild_id, grid)
            payout = base_payout + jackpot_won

            wallet: UserWallet = debit.wallet
            if payout > 0:
                payout = await apply_daily_casino_profit_cap(
                    self._economy_repository,
                    settings,
                    guild_id=guild_id,
                    user_id=user_id,
                    stake=config.cost,
                    payout=payout,
                )
            if payout > 0:
                payment = await self._economy_repository.mutate_balance(
                    guild_id=guild_id,
                    user_id=user_id,
                    amount=payout,
                    transaction_type=EconomyTransactionType.CASINO_PAYOUT,
                    actor_id=None,
                    reason="scratch_card_payout",
                    metadata={
                        "game": "scratch_card",
                        "tier": config.tier.value,
                        "payout": payout,
                        "uncapped_payout": base_payout + jackpot_won,
                        "jackpot_won": jackpot_won,
                        "winning_lines": winning_lines,
                    },
                )
                wallet = payment.wallet
            credit = await self._economy_repository.apply_credit_protection(
                guild_id=guild_id,
                user_id=user_id,
                game_key="scratch_card",
                stake=config.cost,
                is_loss=payout <= 0,
                metadata={"source": "scratch_card", "tier": config.tier.value},
            )
            cashback = credit.cashback_amount
            if credit.wallet is not None:
                wallet = credit.wallet

        await self._unlock_progress(guild_id, user_id, payout, jackpot_won)
        return ScratchCardResult(
            guild_id=guild_id,
            user_id=user_id,
            tier=config.tier,
            tier_label=config.label,
            cost=config.cost,
            grid=grid,
            winning_lines=winning_lines,
            payout=payout,
            jackpot_won=jackpot_won,
            seasonal_theme=seasonal.theme,
            wallet=wallet,
            cashback=cashback,
        )

    async def _resolve_jackpot(
        self,
        guild_id: int,
        grid: list[list[str]],
    ) -> int:
        symbols = [symbol for row in grid for symbol in row]
        if symbols.count(JACKPOT_SYMBOL) != 9:
            return 0
        jackpot = await self._progress_service.claim_scratch_jackpot(guild_id)
        return jackpot.amount

    async def _unlock_progress(
        self,
        guild_id: int,
        user_id: int,
        payout: int,
        jackpot_won: int,
    ) -> None:
        await self._progress_service.unlock(guild_id, user_id, "first_bet")
        await self._progress_service.unlock(guild_id, user_id, "first_scratch")
        if payout > 0:
            await self._progress_service.unlock(guild_id, user_id, "first_win")
            await self._progress_service.unlock(guild_id, user_id, "scratch_win")
        else:
            await self._progress_service.unlock(guild_id, user_id, "first_loss")
        if jackpot_won > 0:
            await self._progress_service.unlock(guild_id, user_id, "scratch_jackpot")
        await self._progress_service.evaluate_user_milestones(guild_id, user_id)

    def _build_grid(
        self,
        theme: SeasonalTheme,
        config: ScratchCardTierConfig,
        *,
        difficulty_bps: int,
    ) -> list[list[str]]:
        symbols = SCRATCH_SYMBOLS[theme]
        grid = self._build_random_grid(symbols)
        winning_lines = self._find_winning_lines(grid)
        if not winning_lines or self._is_jackpot_grid(grid):
            return grid

        base_gate_bps = SCRATCH_WIN_GATE_BPS[config.tier]
        gate_bps = apply_daily_profit_difficulty_to_probability(
            base_gate_bps,
            difficulty_bps,
        )
        if not self._roll_probability(gate_bps):
            return self._build_losing_grid(symbols)

        max_lines = SCRATCH_MAX_WINNING_LINES[config.tier]
        if len(winning_lines) > max_lines:
            return self._build_limited_winning_grid(symbols, max_lines)
        return grid

    def _build_random_grid(self, symbols: Sequence[str]) -> list[list[str]]:
        return [
            [self._rng.choice(symbols) for _ in range(3)],
            [self._rng.choice(symbols) for _ in range(3)],
            [self._rng.choice(symbols) for _ in range(3)],
        ]

    def _build_losing_grid(self, symbols: Sequence[str]) -> list[list[str]]:
        for _ in range(100):
            grid = self._build_random_grid(symbols)
            if not self._find_winning_lines(grid) and not self._is_jackpot_grid(grid):
                return grid
        return [
            [symbols[0], symbols[1], symbols[2]],
            [symbols[2], symbols[3], symbols[4]],
            [symbols[4], symbols[5], symbols[0]],
        ]

    def _build_limited_winning_grid(
        self,
        symbols: Sequence[str],
        max_lines: int,
    ) -> list[list[str]]:
        for _ in range(100):
            grid = self._build_random_grid(symbols)
            winning_lines = self._find_winning_lines(grid)
            if 1 <= len(winning_lines) <= max_lines and not self._is_jackpot_grid(grid):
                return grid
        return [
            [symbols[0], symbols[0], symbols[0]],
            [symbols[1], symbols[2], symbols[3]],
            [symbols[4], symbols[5], symbols[1]],
        ]

    def _roll_probability(self, probability_bps: int) -> bool:
        if probability_bps >= PROFIT_DIFFICULTY_ROLL_MAX:
            return True
        if probability_bps <= 0:
            return False
        return self._rng.randint(1, PROFIT_DIFFICULTY_ROLL_MAX) <= probability_bps

    @staticmethod
    def _find_winning_lines(grid: Sequence[Sequence[str]]) -> list[str]:
        lines: list[str] = []
        for index, row in enumerate(grid, start=1):
            if len(set(row)) == 1:
                lines.append(f"Linha {index}")

        for index in range(3):
            column = [grid[0][index], grid[1][index], grid[2][index]]
            if len(set(column)) == 1:
                lines.append(f"Coluna {index + 1}")

        diagonal_a = [grid[0][0], grid[1][1], grid[2][2]]
        diagonal_b = [grid[0][2], grid[1][1], grid[2][0]]
        if len(set(diagonal_a)) == 1:
            lines.append("Diagonal principal")
        if len(set(diagonal_b)) == 1:
            lines.append("Diagonal secundaria")
        return lines

    async def _validate_daily_profit_limit(
        self,
        guild_id: int,
        user_id: int,
    ) -> None:
        settings = await self._economy_repository.get_guild_settings(guild_id)
        if (
            not settings.casino_limiters_enabled
            or settings.casino_daily_profit_limit <= 0
        ):
            return
        current_profit = await self._economy_repository.get_user_casino_profit_since(
            guild_id,
            user_id,
            current_daily_profit_window_start(),
        )
        if current_profit >= settings.casino_daily_profit_limit:
            raise ScratchCardValidationError(
                "Voce atingiu o teto diario de lucro dos jogos."
            )

    async def _validate_daily_purchase_limit(
        self,
        guild_id: int,
        user_id: int,
    ) -> None:
        purchases_today = (
            await self._economy_repository.count_user_scratch_card_purchases_since(
                guild_id,
                user_id,
                current_daily_profit_window_start(),
            )
        )
        if purchases_today >= SCRATCH_DAILY_PURCHASE_LIMIT:
            raise ScratchCardValidationError(
                f"Voce atingiu o limite diario de {SCRATCH_DAILY_PURCHASE_LIMIT} "
                "raspadinhas."
            )

    async def _daily_profit_difficulty_bps(
        self,
        settings: GuildEconomySettings,
        guild_id: int,
        user_id: int,
    ) -> int:
        if (
            not settings.casino_limiters_enabled
            or settings.casino_daily_profit_limit <= 0
        ):
            return 0
        current_profit = await self._economy_repository.get_user_casino_profit_since(
            guild_id,
            user_id,
            current_daily_profit_window_start(),
        )
        return calculate_daily_profit_difficulty_bps(current_profit, settings)

    @staticmethod
    def _is_jackpot_grid(grid: Sequence[Sequence[str]]) -> bool:
        return all(symbol == JACKPOT_SYMBOL for row in grid for symbol in row)

    @staticmethod
    def _parse_tier(tier: str) -> ScratchCardTierConfig:
        try:
            parsed = ScratchCardTier(tier.strip().lower())
        except ValueError as exc:
            raise ScratchCardValidationError(
                "Tipo invalido. Use bronze, prata, ouro ou diamante."
            ) from exc
        return SCRATCH_CARD_TIERS[parsed]
