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
from app.repositories.economy_repository import SQLiteEconomyRepository
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


class ScratchCardService:
    """Jogo de raspadinha 3x3 com jackpot acumulado."""

    def __init__(
        self,
        economy_repository: SQLiteEconomyRepository,
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
        seasonal = await self._progress_service.get_seasonal_theme(guild_id)

        async with self._lock:
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
            grid = self._build_grid(seasonal.theme)
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
                        "jackpot_won": jackpot_won,
                        "winning_lines": winning_lines,
                    },
                )
                wallet = payment.wallet

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
        else:
            await self._progress_service.unlock(guild_id, user_id, "first_loss")
        if jackpot_won > 0:
            await self._progress_service.unlock(guild_id, user_id, "scratch_jackpot")

    def _build_grid(self, theme: SeasonalTheme) -> list[list[str]]:
        symbols = SCRATCH_SYMBOLS[theme]
        return [
            [self._rng.choice(symbols) for _ in range(3)],
            [self._rng.choice(symbols) for _ in range(3)],
            [self._rng.choice(symbols) for _ in range(3)],
        ]

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

    @staticmethod
    def _parse_tier(tier: str) -> ScratchCardTierConfig:
        try:
            parsed = ScratchCardTier(tier.strip().lower())
        except ValueError as exc:
            raise ScratchCardValidationError(
                "Tipo invalido. Use bronze, prata, ouro ou diamante."
            ) from exc
        return SCRATCH_CARD_TIERS[parsed]
