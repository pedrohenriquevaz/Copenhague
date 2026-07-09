from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.models.casino import (
    CasinoGameResult,
    CasinoGameType,
    CasinoOutcome,
    CasinoUserStats,
    CoinSide,
    DiceMode,
    DuelMode,
    DuelResult,
    RaceMascot,
    RouletteColor,
    SlotSymbol,
)
from app.models.economy import EconomyTransaction, EconomyTransactionType, UserWallet
from app.models.guild_settings import GuildEconomySettings
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.services.economy_limits import (
    PROFIT_DIFFICULTY_ROLL_MAX,
    apply_daily_casino_profit_cap,
    calculate_daily_profit_difficulty_bps,
    current_daily_profit_window_start,
)
from app.services.game_progress_service import GameProgressService


class CasinoServiceError(Exception):
    """Erro base dos jogos de cassino."""


class CasinoValidationError(CasinoServiceError):
    """Erro de validacao dos jogos de cassino."""


SLOT_SYMBOLS: tuple[SlotSymbol, ...] = (
    SlotSymbol("cereja", "🍒", 3),
    SlotSymbol("limao", "🍋", 4),
    SlotSymbol("uva", "🍇", 5),
    SlotSymbol("sino", "🔔", 8),
    SlotSymbol("estrela", "⭐", 10),
    SlotSymbol("diamante", "💎", 20),
    SlotSymbol("sete", "7️⃣", 50),
)

RACE_MASCOT_LABELS = {
    RaceMascot.DRAGAO: "Dragao",
    RaceMascot.LOBO: "Lobo",
    RaceMascot.RAPOSA: "Raposa",
    RaceMascot.TARTARUGA: "Tartaruga",
    RaceMascot.AGUIA: "Aguia",
    RaceMascot.GATO: "Gato",
}


class CasinoService:
    """Jogos instantaneos do arcade de pontos virtuais."""

    MIN_BET = 1
    DEFAULT_COOLDOWN_SECONDS = 5
    COIN_FLIP_PAYOUT_PERCENT = 140
    EASY_DICE_PAYOUT_PERCENT = 190
    EXACT_DICE_PAYOUT_PERCENT = 550

    def __init__(
        self,
        repository: SQLiteEconomyRepository,
        *,
        progress_service: GameProgressService | None = None,
        rng: random.Random | random.SystemRandom | None = None,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._repository = repository
        self._progress_service = progress_service
        self._rng = rng or random.SystemRandom()
        self._cooldown_seconds = cooldown_seconds
        self._cooldowns: dict[tuple[int, int, CasinoGameType], datetime] = {}
        self._lock = asyncio.Lock()

    async def play_coin_flip(
        self,
        *,
        guild_id: int,
        user_id: int,
        bet: int,
        choice: str,
    ) -> CasinoGameResult:
        selected = self._parse_coin_side(choice)
        difficulty_bps = await self._daily_profit_difficulty_bps(guild_id, user_id)
        result = self._rng.choice(list(CoinSide))
        won = selected is result
        if won and self._blocked_by_profit_difficulty(difficulty_bps):
            result = self._opposite_coin_side(selected)
            won = False
        payout = self._percent_payout(bet, self.COIN_FLIP_PAYOUT_PERCENT) if won else 0
        outcome = CasinoOutcome.WON if won else CasinoOutcome.LOST

        return await self._settle_instant_game(
            guild_id=guild_id,
            user_id=user_id,
            game_type=CasinoGameType.COIN_FLIP,
            bet=bet,
            payout=payout,
            outcome=outcome,
            title="Cara ou Coroa",
            result_label=result.value.title(),
            detail_lines=[
                f"Escolha: {selected.value.title()}",
                f"Resultado: {result.value.title()}",
            ],
        )

    async def play_dice(
        self,
        *,
        guild_id: int,
        user_id: int,
        bet: int,
        mode: str,
        value: int | None = None,
    ) -> CasinoGameResult:
        dice_mode = self._parse_dice_mode(mode)
        difficulty_bps = await self._daily_profit_difficulty_bps(guild_id, user_id)
        roll = self._rng.randint(1, 6)
        won, multiplier_percent, choice_label = self._resolve_dice_bet(
            dice_mode,
            roll,
            value,
        )
        if won and self._blocked_by_profit_difficulty(difficulty_bps):
            roll = self._losing_dice_roll(dice_mode, value)
            won, multiplier_percent, choice_label = self._resolve_dice_bet(
                dice_mode,
                roll,
                value,
            )
        payout = self._percent_payout(bet, multiplier_percent) if won else 0
        outcome = CasinoOutcome.WON if won else CasinoOutcome.LOST

        return await self._settle_instant_game(
            guild_id=guild_id,
            user_id=user_id,
            game_type=CasinoGameType.DICE,
            bet=bet,
            payout=payout,
            outcome=outcome,
            title="Dados",
            result_label=str(roll),
            detail_lines=[
                f"Modo: {self._format_dice_mode(dice_mode)}",
                f"Aposta: {choice_label}",
                f"Resultado: {roll}",
            ],
        )

    async def play_slot(
        self,
        *,
        guild_id: int,
        user_id: int,
        bet: int,
    ) -> CasinoGameResult:
        difficulty_bps = await self._daily_profit_difficulty_bps(guild_id, user_id)
        symbols = [self._rng.choice(SLOT_SYMBOLS) for _ in range(3)]
        payout, outcome, result_label = self._resolve_slot(symbols, bet)
        if outcome is CasinoOutcome.WON and self._blocked_by_profit_difficulty(
            difficulty_bps,
        ):
            symbols = self._losing_slot_symbols()
            payout, outcome, result_label = self._resolve_slot(symbols, bet)

        return await self._settle_instant_game(
            guild_id=guild_id,
            user_id=user_id,
            game_type=CasinoGameType.SLOT,
            bet=bet,
            payout=payout,
            outcome=outcome,
            title="Slot Machine",
            result_label=result_label,
            detail_lines=[
                "Resultado: " + " | ".join(symbol.label for symbol in symbols),
            ],
        )

    async def play_roulette(
        self,
        *,
        guild_id: int,
        user_id: int,
        bet: int,
        color: str,
    ) -> CasinoGameResult:
        selected = self._parse_roulette_color(color)
        difficulty_bps = await self._daily_profit_difficulty_bps(guild_id, user_id)
        result = self._draw_roulette_color()
        won = selected is result
        if won and self._blocked_by_profit_difficulty(difficulty_bps):
            result = self._losing_roulette_color(selected)
            won = False
        multiplier = 10 if result is RouletteColor.VERDE else 2
        payout = bet * multiplier if won else 0
        outcome = CasinoOutcome.WON if won else CasinoOutcome.LOST

        return await self._settle_instant_game(
            guild_id=guild_id,
            user_id=user_id,
            game_type=CasinoGameType.ROULETTE,
            bet=bet,
            payout=payout,
            outcome=outcome,
            title="Roleta",
            result_label=self._format_roulette_color(result),
            detail_lines=[
                f"Cor escolhida: {self._format_roulette_color(selected)}",
                f"Resultado: {self._format_roulette_color(result)}",
            ],
        )

    async def play_mascot_race(
        self,
        *,
        guild_id: int,
        user_id: int,
        bet: int,
        mascot: str,
    ) -> CasinoGameResult:
        selected = self._parse_race_mascot(mascot)
        difficulty_bps = await self._daily_profit_difficulty_bps(guild_id, user_id)
        winner = self._rng.choice(list(RaceMascot))
        won = selected is winner
        if won and self._blocked_by_profit_difficulty(difficulty_bps):
            winner = self._losing_race_mascot(selected)
            won = False
        payout = bet * 5 if won else 0
        outcome = CasinoOutcome.WON if won else CasinoOutcome.LOST

        return await self._settle_instant_game(
            guild_id=guild_id,
            user_id=user_id,
            game_type=CasinoGameType.MASCOT_RACE,
            bet=bet,
            payout=payout,
            outcome=outcome,
            title="Corrida de Mascotes",
            result_label=self._format_race_mascot(winner),
            detail_lines=[
                f"Sua aposta: {self._format_race_mascot(selected)}",
                f"Vencedor: {self._format_race_mascot(winner)}",
            ],
        )

    async def validate_duel_challenge(
        self,
        *,
        guild_id: int,
        challenger_id: int,
        challenged_id: int,
        bet: int,
        mode: str,
    ) -> DuelMode:
        duel_mode = self._parse_duel_mode(mode)
        self._validate_duel_users(challenger_id, challenged_id)
        settings = await self._repository.get_guild_settings(guild_id)
        self._validate_bet(
            bet,
            settings.casino_min_bet_duel,
            settings.casino_max_bet,
        )
        await self._validate_daily_profit_limit(settings, guild_id, challenger_id)
        await self._validate_daily_profit_limit(settings, guild_id, challenged_id)
        self._validate_not_on_cooldown(guild_id, challenger_id, CasinoGameType.DUEL)
        self._validate_not_on_cooldown(guild_id, challenged_id, CasinoGameType.DUEL)
        await self._require_wallet_balance(guild_id, challenger_id, bet)
        await self._require_wallet_balance(guild_id, challenged_id, bet)
        return duel_mode

    async def resolve_duel(
        self,
        *,
        guild_id: int,
        challenger_id: int,
        challenged_id: int,
        bet: int,
        mode: str,
    ) -> DuelResult:
        duel_mode = self._parse_duel_mode(mode)
        self._validate_duel_users(challenger_id, challenged_id)

        async with self._lock:
            settings = await self._repository.get_guild_settings(guild_id)
            self._validate_bet(
                bet,
                settings.casino_min_bet_duel,
                settings.casino_max_bet,
            )
            await self._validate_daily_profit_limit(settings, guild_id, challenger_id)
            await self._validate_daily_profit_limit(settings, guild_id, challenged_id)
            self._validate_not_on_cooldown(guild_id, challenger_id, CasinoGameType.DUEL)
            self._validate_not_on_cooldown(guild_id, challenged_id, CasinoGameType.DUEL)
            await self._require_wallet_balance(guild_id, challenger_id, bet)
            await self._require_wallet_balance(guild_id, challenged_id, bet)
            await self._debit_bet(guild_id, challenger_id, CasinoGameType.DUEL, bet)
            try:
                await self._debit_bet(guild_id, challenged_id, CasinoGameType.DUEL, bet)
            except CasinoValidationError:
                await self._refund_bet(
                    guild_id, challenger_id, CasinoGameType.DUEL, bet
                )
                raise

            winner_id, outcome, result_label, detail_lines = self._resolve_duel_result(
                challenger_id,
                challenged_id,
                duel_mode,
            )

            if winner_id is None:
                payout = bet
                challenger_wallet, _ = await self._pay_out(
                    guild_id,
                    challenger_id,
                    CasinoGameType.DUEL,
                    bet,
                    bet,
                    CasinoOutcome.DRAW,
                )
                challenged_wallet, _ = await self._pay_out(
                    guild_id,
                    challenged_id,
                    CasinoGameType.DUEL,
                    bet,
                    bet,
                    CasinoOutcome.DRAW,
                )
            else:
                payout = bet * 2
                winner_wallet, payout = await self._pay_out(
                    guild_id,
                    winner_id,
                    CasinoGameType.DUEL,
                    bet,
                    payout,
                    CasinoOutcome.WON,
                )

            self._set_cooldown(guild_id, challenger_id, CasinoGameType.DUEL)
            self._set_cooldown(guild_id, challenged_id, CasinoGameType.DUEL)

        if winner_id is not None:
            if winner_id == challenger_id:
                challenger_wallet = winner_wallet
                challenged_wallet = await self._repository.get_wallet(
                    guild_id,
                    challenged_id,
                )
            else:
                challenger_wallet = await self._repository.get_wallet(
                    guild_id,
                    challenger_id,
                )
                challenged_wallet = winner_wallet
        result = DuelResult(
            guild_id=guild_id,
            challenger_id=challenger_id,
            challenged_id=challenged_id,
            mode=duel_mode,
            bet=bet,
            winner_id=winner_id,
            payout=payout,
            outcome=outcome,
            result_label=result_label,
            detail_lines=detail_lines,
            challenger_wallet=challenger_wallet,
            challenged_wallet=challenged_wallet,
        )
        await self._unlock_duel_progress(result)
        return result

    async def list_history(
        self,
        guild_id: int,
        user_id: int,
        *,
        limit: int = 10,
    ) -> list[EconomyTransaction]:
        transactions = await self._repository.list_transactions(
            guild_id,
            user_id,
            limit=50,
        )
        casino_transactions = [
            transaction
            for transaction in transactions
            if transaction.type
            in {
                EconomyTransactionType.CASINO_BET,
                EconomyTransactionType.CASINO_PAYOUT,
                EconomyTransactionType.REFUND,
            }
        ]
        return casino_transactions[: max(1, min(limit, 25))]

    async def get_user_stats(
        self,
        guild_id: int,
        user_id: int,
    ) -> CasinoUserStats:
        transactions = await self._repository.list_casino_transactions(guild_id)
        return self._build_user_stats(
            guild_id,
            user_id,
            [
                transaction
                for transaction in transactions
                if transaction.user_id == user_id
            ],
        )

    async def list_profit_ranking(
        self,
        guild_id: int,
        *,
        limit: int = 10,
    ) -> list[CasinoUserStats]:
        transactions = await self._repository.list_casino_transactions(guild_id)
        user_ids = sorted({transaction.user_id for transaction in transactions})
        stats = [
            self._build_user_stats(
                guild_id,
                user_id,
                [
                    transaction
                    for transaction in transactions
                    if transaction.user_id == user_id
                ],
            )
            for user_id in user_ids
        ]
        ranked = sorted(
            stats,
            key=lambda item: (item.net_profit, item.total_payout_amount),
            reverse=True,
        )
        return ranked[: max(1, min(limit, 25))]

    async def reset_user_state(self, guild_id: int, user_id: int) -> None:
        async with self._lock:
            for key in list(self._cooldowns):
                if key[0] == guild_id and key[1] == user_id:
                    self._cooldowns.pop(key, None)

    async def _settle_instant_game(
        self,
        *,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
        bet: int,
        payout: int,
        outcome: CasinoOutcome,
        title: str,
        result_label: str,
        detail_lines: list[str],
    ) -> CasinoGameResult:
        async with self._lock:
            await self._validate_can_play(guild_id, user_id, game_type, bet)
            debit_wallet = await self._debit_bet(guild_id, user_id, game_type, bet)
            wallet = debit_wallet
            if payout > 0:
                wallet, payout = await self._pay_out(
                    guild_id,
                    user_id,
                    game_type,
                    bet,
                    payout,
                    outcome,
                )
            self._set_cooldown(guild_id, user_id, game_type)

        result = CasinoGameResult(
            guild_id=guild_id,
            user_id=user_id,
            game_type=game_type,
            bet=bet,
            payout=payout,
            profit=payout - bet,
            outcome=outcome,
            title=title,
            result_label=result_label,
            detail_lines=detail_lines,
            wallet=wallet,
        )
        await self._unlock_instant_game_progress(result)
        return result

    async def _unlock_instant_game_progress(self, result: CasinoGameResult) -> None:
        if self._progress_service is None:
            return

        await self._progress_service.unlock(
            result.guild_id,
            result.user_id,
            "first_bet",
        )
        game_achievement_keys = {
            CasinoGameType.COIN_FLIP: "first_coin_flip",
            CasinoGameType.DICE: "first_dice",
            CasinoGameType.SLOT: "first_slot",
            CasinoGameType.ROULETTE: "first_roulette",
            CasinoGameType.MASCOT_RACE: "first_mascot_race",
        }
        achievement_key = game_achievement_keys.get(result.game_type)
        if achievement_key is not None:
            await self._progress_service.unlock(
                result.guild_id,
                result.user_id,
                achievement_key,
            )

        if result.outcome is CasinoOutcome.WON:
            await self._progress_service.unlock(
                result.guild_id,
                result.user_id,
                "first_win",
            )
        elif result.outcome is CasinoOutcome.LOST:
            await self._progress_service.unlock(
                result.guild_id,
                result.user_id,
                "first_loss",
            )
        await self._progress_service.evaluate_user_milestones(
            result.guild_id,
            result.user_id,
        )

    async def _unlock_duel_progress(self, result: DuelResult) -> None:
        if self._progress_service is None:
            return

        participant_ids = (result.challenger_id, result.challenged_id)
        for user_id in participant_ids:
            await self._progress_service.unlock(result.guild_id, user_id, "first_bet")
            await self._progress_service.unlock(result.guild_id, user_id, "first_duel")

        if result.winner_id is not None:
            loser_id = (
                result.challenged_id
                if result.winner_id == result.challenger_id
                else result.challenger_id
            )
            await self._progress_service.unlock(
                result.guild_id,
                result.winner_id,
                "first_win",
            )
            await self._progress_service.unlock(
                result.guild_id,
                result.winner_id,
                "duel_win",
            )
            await self._progress_service.unlock(result.guild_id, loser_id, "first_loss")

        for user_id in participant_ids:
            await self._progress_service.evaluate_user_milestones(
                result.guild_id,
                user_id,
            )

    async def _validate_can_play(
        self,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
        bet: int,
    ) -> None:
        settings = await self._repository.get_guild_settings(guild_id)
        self._validate_bet(
            bet,
            self._min_bet_for_game(settings, game_type),
            settings.casino_max_bet,
        )
        await self._validate_daily_profit_limit(settings, guild_id, user_id)
        self._validate_not_on_cooldown(guild_id, user_id, game_type)

        wallet = await self._repository.get_wallet(guild_id, user_id)
        if wallet.balance < bet:
            raise CasinoValidationError("Saldo insuficiente para essa aposta.")

    def _validate_not_on_cooldown(
        self,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
    ) -> None:
        remaining = self._remaining_cooldown(guild_id, user_id, game_type)
        if remaining > 0:
            game_name = self._format_game(game_type)
            raise CasinoValidationError(
                f"Aguarde {remaining}s para jogar {game_name} de novo."
            )

    async def _require_wallet_balance(
        self,
        guild_id: int,
        user_id: int,
        amount: int,
    ) -> None:
        wallet = await self._repository.get_wallet(guild_id, user_id)
        if wallet.balance < amount:
            raise CasinoValidationError(f"<@{user_id}> nao possui saldo suficiente.")

    async def _debit_bet(
        self,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
        bet: int,
    ) -> UserWallet:
        try:
            result = await self._repository.mutate_balance(
                guild_id=guild_id,
                user_id=user_id,
                amount=-bet,
                transaction_type=EconomyTransactionType.CASINO_BET,
                actor_id=None,
                reason=f"{game_type.value}_bet",
                metadata={"game": game_type.value, "bet": bet},
            )
        except ValueError as exc:
            raise CasinoValidationError("Saldo insuficiente para essa aposta.") from exc
        return result.wallet

    async def _refund_bet(
        self,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
        amount: int,
    ) -> UserWallet:
        result = await self._repository.mutate_balance(
            guild_id=guild_id,
            user_id=user_id,
            amount=amount,
            transaction_type=EconomyTransactionType.REFUND,
            actor_id=None,
            reason=f"{game_type.value}_refund",
            metadata={"game": game_type.value, "bet": amount},
        )
        return result.wallet

    async def _pay_out(
        self,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
        bet: int,
        payout: int,
        outcome: CasinoOutcome,
    ) -> tuple[UserWallet, int]:
        settings = await self._repository.get_guild_settings(guild_id)
        capped_payout = await apply_daily_casino_profit_cap(
            self._repository,
            settings,
            guild_id=guild_id,
            user_id=user_id,
            stake=bet,
            payout=payout,
        )
        if capped_payout <= 0:
            return await self._repository.get_wallet(guild_id, user_id), 0
        result = await self._repository.mutate_balance(
            guild_id=guild_id,
            user_id=user_id,
            amount=capped_payout,
            transaction_type=EconomyTransactionType.CASINO_PAYOUT,
            actor_id=None,
            reason=f"{game_type.value}_payout",
            metadata={
                "game": game_type.value,
                "bet": bet,
                "payout": capped_payout,
                "uncapped_payout": payout,
                "outcome": outcome.value,
            },
        )
        return result.wallet, capped_payout

    async def _validate_daily_profit_limit(
        self,
        settings: GuildEconomySettings,
        guild_id: int,
        user_id: int,
    ) -> None:
        if (
            not settings.casino_limiters_enabled
            or settings.casino_daily_profit_limit <= 0
        ):
            return
        current_profit = await self._repository.get_user_casino_profit_since(
            guild_id,
            user_id,
            current_daily_profit_window_start(),
        )
        if current_profit >= settings.casino_daily_profit_limit:
            raise CasinoValidationError(
                "Voce atingiu o teto diario de lucro dos jogos."
            )

    async def _daily_profit_difficulty_bps(self, guild_id: int, user_id: int) -> int:
        settings = await self._repository.get_guild_settings(guild_id)
        if (
            not settings.casino_limiters_enabled
            or settings.casino_daily_profit_limit <= 0
        ):
            return 0
        current_profit = await self._repository.get_user_casino_profit_since(
            guild_id,
            user_id,
            current_daily_profit_window_start(),
        )
        return calculate_daily_profit_difficulty_bps(current_profit, settings)

    def _blocked_by_profit_difficulty(self, difficulty_bps: int) -> bool:
        if difficulty_bps <= 0:
            return False
        return self._rng.randint(1, PROFIT_DIFFICULTY_ROLL_MAX) <= difficulty_bps

    def _remaining_cooldown(
        self,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
    ) -> int:
        if self._cooldown_seconds <= 0:
            return 0

        key = (guild_id, user_id, game_type)
        last_played_at = self._cooldowns.get(key)
        if last_played_at is None:
            return 0

        available_at = last_played_at + timedelta(seconds=self._cooldown_seconds)
        remaining = int((available_at - datetime.now(UTC)).total_seconds())
        return max(0, remaining + 1)

    def _set_cooldown(
        self,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
    ) -> None:
        if self._cooldown_seconds > 0:
            self._cooldowns[(guild_id, user_id, game_type)] = datetime.now(UTC)

    @classmethod
    def _validate_bet(cls, bet: int, min_bet: int, max_bet: int) -> None:
        if bet < min_bet:
            raise CasinoValidationError(f"A aposta minima e {min_bet}.")
        if bet > max_bet:
            raise CasinoValidationError(f"A aposta maxima e {max_bet}.")

    @staticmethod
    def _min_bet_for_game(
        settings: GuildEconomySettings,
        game_type: CasinoGameType,
    ) -> int:
        min_bets = {
            CasinoGameType.COIN_FLIP: settings.casino_min_bet_coin_flip,
            CasinoGameType.DICE: settings.casino_min_bet_dice,
            CasinoGameType.SLOT: settings.casino_min_bet_slot,
            CasinoGameType.ROULETTE: settings.casino_min_bet_roulette,
            CasinoGameType.MASCOT_RACE: settings.casino_min_bet_mascot_race,
            CasinoGameType.DUEL: settings.casino_min_bet_duel,
            CasinoGameType.BLACKJACK: settings.casino_min_bet_blackjack,
        }
        return min_bets[game_type]

    @staticmethod
    def _parse_coin_side(choice: str) -> CoinSide:
        try:
            return CoinSide(choice.strip().lower())
        except ValueError as exc:
            raise CasinoValidationError("Escolha invalida. Use cara ou coroa.") from exc

    @staticmethod
    def _opposite_coin_side(side: CoinSide) -> CoinSide:
        return CoinSide.COROA if side is CoinSide.CARA else CoinSide.CARA

    @staticmethod
    def _parse_dice_mode(mode: str) -> DiceMode:
        try:
            return DiceMode(mode.strip().lower())
        except ValueError as exc:
            raise CasinoValidationError(
                "Modo invalido. Use numero, par, impar, maior ou menor."
            ) from exc

    @staticmethod
    def _parse_roulette_color(color: str) -> RouletteColor:
        try:
            return RouletteColor(color.strip().lower())
        except ValueError as exc:
            raise CasinoValidationError(
                "Cor invalida. Use vermelho, preto ou verde."
            ) from exc

    @staticmethod
    def _parse_duel_mode(mode: str) -> DuelMode:
        try:
            return DuelMode(mode.strip().lower())
        except ValueError as exc:
            raise CasinoValidationError("Modo invalido. Use sorte ou dados.") from exc

    @staticmethod
    def _parse_race_mascot(mascot: str) -> RaceMascot:
        try:
            return RaceMascot(mascot.strip().lower())
        except ValueError as exc:
            raise CasinoValidationError(
                "Mascote invalido. Use dragao, lobo, raposa, tartaruga, aguia ou gato."
            ) from exc

    def _draw_roulette_color(self) -> RouletteColor:
        roll = self._rng.randint(1, 1000)
        if roll <= 475:
            return RouletteColor.VERMELHO
        if roll <= 950:
            return RouletteColor.PRETO
        return RouletteColor.VERDE

    @staticmethod
    def _losing_roulette_color(selected: RouletteColor) -> RouletteColor:
        if selected is RouletteColor.VERMELHO:
            return RouletteColor.PRETO
        return RouletteColor.VERMELHO

    @staticmethod
    def _resolve_dice_bet(
        mode: DiceMode,
        roll: int,
        value: int | None,
    ) -> tuple[bool, int, str]:
        if mode is DiceMode.NUMERO:
            if value is None or value < 1 or value > 6:
                raise CasinoValidationError("No modo numero, informe valor de 1 a 6.")
            return roll == value, CasinoService.EXACT_DICE_PAYOUT_PERCENT, str(value)
        if mode is DiceMode.PAR:
            return roll % 2 == 0, CasinoService.EASY_DICE_PAYOUT_PERCENT, "Par"
        if mode is DiceMode.IMPAR:
            return roll % 2 == 1, CasinoService.EASY_DICE_PAYOUT_PERCENT, "Impar"
        if mode is DiceMode.MAIOR:
            return roll > 3, CasinoService.EASY_DICE_PAYOUT_PERCENT, "Maior que 3"
        return roll <= 3, CasinoService.EASY_DICE_PAYOUT_PERCENT, "Menor ou igual a 3"

    @staticmethod
    def _losing_dice_roll(mode: DiceMode, value: int | None) -> int:
        if mode is DiceMode.NUMERO:
            return 1 if value != 1 else 2
        if mode is DiceMode.PAR:
            return 1
        if mode is DiceMode.IMPAR:
            return 2
        if mode is DiceMode.MAIOR:
            return 3
        return 4

    @staticmethod
    def _percent_payout(bet: int, percent: int) -> int:
        return max(1, (bet * percent) // 100)

    @staticmethod
    def _resolve_slot(
        symbols: Sequence[SlotSymbol],
        bet: int,
    ) -> tuple[int, CasinoOutcome, str]:
        if len(symbols) != 3:
            raise CasinoValidationError("A slot precisa sortear 3 simbolos.")

        counts = {
            symbol.key: sum(1 for item in symbols if item.key == symbol.key)
            for symbol in symbols
        }
        if 3 in counts.values():
            symbol = symbols[0]
            payout = bet * symbol.triple_multiplier
            return payout, CasinoOutcome.WON, f"Triplo {symbol.label}"
        if 2 in counts.values():
            payout = max(1, bet // 5)
            return payout, CasinoOutcome.LOST, "Quase"
        return 0, CasinoOutcome.LOST, "Sem combinacao"

    @staticmethod
    def _losing_slot_symbols() -> list[SlotSymbol]:
        return [SLOT_SYMBOLS[0], SLOT_SYMBOLS[1], SLOT_SYMBOLS[2]]

    @staticmethod
    def _losing_race_mascot(selected: RaceMascot) -> RaceMascot:
        return next(mascot for mascot in RaceMascot if mascot is not selected)

    def _resolve_duel_result(
        self,
        challenger_id: int,
        challenged_id: int,
        mode: DuelMode,
    ) -> tuple[int | None, CasinoOutcome, str, list[str]]:
        if mode is DuelMode.SORTE:
            winner_id = self._rng.choice([challenger_id, challenged_id])
            return (
                winner_id,
                CasinoOutcome.WON,
                "Sorte",
                ["Modo: Sorte", f"Vencedor: <@{winner_id}>"],
            )

        challenger_roll = self._rng.randint(1, 6)
        challenged_roll = self._rng.randint(1, 6)
        details = [
            "Modo: Dados",
            f"Desafiante: {challenger_roll}",
            f"Desafiado: {challenged_roll}",
        ]
        if challenger_roll == challenged_roll:
            return None, CasinoOutcome.DRAW, "Empate nos dados", details
        winner_id = (
            challenger_id if challenger_roll > challenged_roll else challenged_id
        )
        return winner_id, CasinoOutcome.WON, "Dados", details

    @staticmethod
    def _format_dice_mode(mode: DiceMode) -> str:
        labels = {
            DiceMode.NUMERO: "Numero exato",
            DiceMode.PAR: "Par",
            DiceMode.IMPAR: "Impar",
            DiceMode.MAIOR: "Maior",
            DiceMode.MENOR: "Menor",
        }
        return labels[mode]

    @staticmethod
    def _format_game(game_type: CasinoGameType) -> str:
        labels = {
            CasinoGameType.COIN_FLIP: "Cara ou Coroa",
            CasinoGameType.DICE: "Dados",
            CasinoGameType.SLOT: "Slot Machine",
            CasinoGameType.ROULETTE: "Roleta",
            CasinoGameType.DUEL: "Duelo",
            CasinoGameType.MASCOT_RACE: "Corrida de Mascotes",
            CasinoGameType.BLACKJACK: "BlackJack",
        }
        return labels[game_type]

    @staticmethod
    def _format_roulette_color(color: RouletteColor) -> str:
        labels = {
            RouletteColor.VERMELHO: "Vermelho 🟥",
            RouletteColor.PRETO: "Preto ⬛",
            RouletteColor.VERDE: "Verde 🟩",
        }
        return labels[color]

    @staticmethod
    def _format_race_mascot(mascot: RaceMascot) -> str:
        return RACE_MASCOT_LABELS[mascot]

    @staticmethod
    def _validate_duel_users(challenger_id: int, challenged_id: int) -> None:
        if challenger_id == challenged_id:
            raise CasinoValidationError("Voce nao pode desafiar a si mesmo.")

    @staticmethod
    def _build_user_stats(
        guild_id: int,
        user_id: int,
        transactions: list[EconomyTransaction],
    ) -> CasinoUserStats:
        total_bet_amount = sum(
            -transaction.amount
            for transaction in transactions
            if transaction.type is EconomyTransactionType.CASINO_BET
        )
        total_payout_amount = sum(
            transaction.amount
            for transaction in transactions
            if transaction.amount > 0
            and transaction.type
            in {EconomyTransactionType.CASINO_PAYOUT, EconomyTransactionType.REFUND}
        )
        biggest_win = max(
            [
                transaction.amount
                for transaction in transactions
                if transaction.type is EconomyTransactionType.CASINO_PAYOUT
                and transaction.metadata.get("outcome")
                in {
                    CasinoOutcome.WON.value,
                    "PLAYER_WIN",
                    "PLAYER_BLACKJACK",
                }
            ],
            default=0,
        )
        biggest_loss = max(
            [
                -transaction.amount
                for transaction in transactions
                if transaction.type is EconomyTransactionType.CASINO_BET
            ],
            default=0,
        )
        return CasinoUserStats(
            guild_id=guild_id,
            user_id=user_id,
            total_games_played=sum(
                1
                for transaction in transactions
                if transaction.type is EconomyTransactionType.CASINO_BET
            ),
            total_bet_amount=total_bet_amount,
            total_payout_amount=total_payout_amount,
            net_profit=sum(transaction.amount for transaction in transactions),
            biggest_win=biggest_win,
            biggest_loss=biggest_loss,
        )
