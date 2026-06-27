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
from app.repositories.economy_repository import SQLiteEconomyRepository


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
    MAX_BET = 100_000
    DEFAULT_COOLDOWN_SECONDS = 5

    def __init__(
        self,
        repository: SQLiteEconomyRepository,
        *,
        rng: random.Random | random.SystemRandom | None = None,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._repository = repository
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
        result = self._rng.choice(list(CoinSide))
        won = selected is result
        payout = bet * 2 if won else 0
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
        roll = self._rng.randint(1, 6)
        won, multiplier, choice_label = self._resolve_dice_bet(
            dice_mode,
            roll,
            value,
        )
        payout = bet * multiplier if won else 0
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
        symbols = [self._rng.choice(SLOT_SYMBOLS) for _ in range(3)]
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
        result = self._draw_roulette_color()
        won = selected is result
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
        winner = self._rng.choice(list(RaceMascot))
        won = selected is winner
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
        self._validate_bet(bet)
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
            self._validate_bet(bet)
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
                await self._pay_out(
                    guild_id,
                    challenger_id,
                    CasinoGameType.DUEL,
                    bet,
                    bet,
                    CasinoOutcome.DRAW,
                )
                await self._pay_out(
                    guild_id,
                    challenged_id,
                    CasinoGameType.DUEL,
                    bet,
                    bet,
                    CasinoOutcome.DRAW,
                )
            else:
                payout = bet * 2
                await self._pay_out(
                    guild_id,
                    winner_id,
                    CasinoGameType.DUEL,
                    bet,
                    payout,
                    CasinoOutcome.WON,
                )

            self._set_cooldown(guild_id, challenger_id, CasinoGameType.DUEL)
            self._set_cooldown(guild_id, challenged_id, CasinoGameType.DUEL)

        challenger_wallet = await self._repository.get_wallet(guild_id, challenger_id)
        challenged_wallet = await self._repository.get_wallet(guild_id, challenged_id)
        return DuelResult(
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
                wallet = await self._pay_out(
                    guild_id,
                    user_id,
                    game_type,
                    bet,
                    payout,
                    outcome,
                )
            self._set_cooldown(guild_id, user_id, game_type)

        return CasinoGameResult(
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

    async def _validate_can_play(
        self,
        guild_id: int,
        user_id: int,
        game_type: CasinoGameType,
        bet: int,
    ) -> None:
        self._validate_bet(bet)
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
    ) -> UserWallet:
        result = await self._repository.mutate_balance(
            guild_id=guild_id,
            user_id=user_id,
            amount=payout,
            transaction_type=EconomyTransactionType.CASINO_PAYOUT,
            actor_id=None,
            reason=f"{game_type.value}_payout",
            metadata={
                "game": game_type.value,
                "bet": bet,
                "payout": payout,
                "outcome": outcome.value,
            },
        )
        return result.wallet

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
    def _validate_bet(cls, bet: int) -> None:
        if bet < cls.MIN_BET:
            raise CasinoValidationError(f"A aposta minima e {cls.MIN_BET}.")
        if bet > cls.MAX_BET:
            raise CasinoValidationError(f"A aposta maxima e {cls.MAX_BET}.")

    @staticmethod
    def _parse_coin_side(choice: str) -> CoinSide:
        try:
            return CoinSide(choice.strip().lower())
        except ValueError as exc:
            raise CasinoValidationError("Escolha invalida. Use cara ou coroa.") from exc

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
    def _resolve_dice_bet(
        mode: DiceMode,
        roll: int,
        value: int | None,
    ) -> tuple[bool, int, str]:
        if mode is DiceMode.NUMERO:
            if value is None or value < 1 or value > 6:
                raise CasinoValidationError("No modo numero, informe valor de 1 a 6.")
            return roll == value, 6, str(value)
        if mode is DiceMode.PAR:
            return roll % 2 == 0, 2, "Par"
        if mode is DiceMode.IMPAR:
            return roll % 2 == 1, 2, "Impar"
        if mode is DiceMode.MAIOR:
            return roll > 3, 2, "Maior que 3"
        return roll <= 3, 2, "Menor ou igual a 3"

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
