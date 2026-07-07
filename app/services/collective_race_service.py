from __future__ import annotations

import asyncio
import random
from datetime import timedelta

from app.models.casino import RaceMascot
from app.models.economy import EconomyTransactionType
from app.models.game_progress import (
    CollectiveRaceBet,
    CollectiveRaceBetCreate,
    CollectiveRaceBetStatus,
    CollectiveRaceCreate,
    CollectiveRacePlacementResult,
    CollectiveRaceSession,
    CollectiveRaceSettlementResult,
)
from app.models.giveaway import utc_now
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.repositories.game_progress_repository import GameProgressRepositoryProtocol
from app.services.game_progress_service import GameProgressService


class CollectiveRaceServiceError(Exception):
    """Erro base da corrida coletiva."""


class CollectiveRaceValidationError(CollectiveRaceServiceError):
    """Erro de validacao da corrida coletiva."""


class CollectiveRaceService:
    """Corrida coletiva de mascotes com apostas por janela de tempo."""

    MIN_STAKE = 1
    MAX_STAKE = 100_000
    MIN_DURATION_SECONDS = 10
    MAX_DURATION_SECONDS = 3600
    PAYOUT_MULTIPLIER = 5

    def __init__(
        self,
        repository: GameProgressRepositoryProtocol,
        economy_repository: SQLiteEconomyRepository,
        progress_service: GameProgressService,
        *,
        rng: random.Random | random.SystemRandom | None = None,
    ) -> None:
        self._repository = repository
        self._economy_repository = economy_repository
        self._progress_service = progress_service
        self._rng = rng or random.SystemRandom()
        self._lock = asyncio.Lock()

    async def create_race(
        self,
        *,
        guild_id: int,
        opened_by: int,
        stake: int,
        duration_seconds: int,
        channel_id: int | None = None,
        message_id: int | None = None,
    ) -> CollectiveRaceSession:
        self._validate_stake(stake)
        self._validate_duration(duration_seconds)
        opened_at = utc_now()
        return await self._repository.create_collective_race(
            CollectiveRaceCreate(
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
                stake=stake,
                opened_by=opened_by,
                opened_at=opened_at,
                closes_at=opened_at + timedelta(seconds=duration_seconds),
            )
        )

    async def publish_race(
        self,
        race_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> CollectiveRaceSession:
        return await self._repository.publish_collective_race(
            race_id,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def get_race(self, race_id: int) -> CollectiveRaceSession | None:
        return await self._repository.get_collective_race(race_id)

    async def list_open_races(self, guild_id: int) -> list[CollectiveRaceSession]:
        return await self._repository.list_open_collective_races(guild_id)

    async def place_bet(
        self,
        *,
        guild_id: int,
        user_id: int,
        race_id: int,
        mascot: str,
    ) -> CollectiveRacePlacementResult:
        selected = self.parse_mascot(mascot)

        async with self._lock:
            race = await self._require_open_race(guild_id, race_id)
            if utc_now() >= race.closes_at:
                raise CollectiveRaceValidationError(
                    "A janela de apostas desta corrida ja fechou."
                )
            try:
                debit = await self._economy_repository.mutate_balance(
                    guild_id=guild_id,
                    user_id=user_id,
                    amount=-race.stake,
                    transaction_type=EconomyTransactionType.CASINO_BET,
                    actor_id=None,
                    reason="collective_race_bet",
                    metadata={
                        "game": "collective_race",
                        "race_id": race.id,
                        "mascot": selected.value,
                    },
                )
            except ValueError as exc:
                raise CollectiveRaceValidationError(
                    "Saldo insuficiente para essa aposta."
                ) from exc

            try:
                bet = await self._repository.create_collective_race_bet(
                    CollectiveRaceBetCreate(
                        race_id=race.id,
                        guild_id=guild_id,
                        user_id=user_id,
                        mascot=selected,
                        stake=race.stake,
                        potential_payout=race.stake * self.PAYOUT_MULTIPLIER,
                        debit_transaction_id=debit.transaction.id,
                        created_at=utc_now(),
                    )
                )
            except ValueError as exc:
                await self._refund_bet(
                    bet=None,
                    guild_id=guild_id,
                    user_id=user_id,
                    amount=race.stake,
                    race_id=race.id,
                )
                raise CollectiveRaceValidationError(str(exc)) from exc

        await self._progress_service.unlock(guild_id, user_id, "first_bet")
        wallet = await self._economy_repository.get_wallet(guild_id, user_id)
        return CollectiveRacePlacementResult(race=race, bet=bet, wallet=wallet)

    async def finish_race(
        self,
        *,
        guild_id: int,
        race_id: int,
        winner: str | None = None,
        cancel: bool = False,
    ) -> CollectiveRaceSettlementResult:
        async with self._lock:
            race = await self._require_race(guild_id, race_id)
            selected_winner = None if cancel else self._resolve_winner(winner)
            settled_race, bets = await self._repository.settle_collective_race(
                race.id,
                winner=selected_winner,
                cancelled=cancel,
            )
            if settled_race is None:
                raise CollectiveRaceValidationError("Corrida coletiva nao encontrada.")

            total_paid = 0
            total_refunded = 0
            for bet in bets:
                if bet.status is CollectiveRaceBetStatus.WON:
                    transaction_id = await self._pay_bet(bet)
                    await self._repository.mark_collective_race_bet_paid(
                        bet.id,
                        transaction_id=transaction_id,
                    )
                    total_paid += bet.potential_payout
                    await self._progress_service.unlock(
                        bet.guild_id,
                        bet.user_id,
                        "first_win",
                    )
                    await self._progress_service.unlock(
                        bet.guild_id,
                        bet.user_id,
                        "collective_race_win",
                    )
                elif bet.status is CollectiveRaceBetStatus.LOST:
                    await self._progress_service.unlock(
                        bet.guild_id,
                        bet.user_id,
                        "first_loss",
                    )
                elif bet.status is CollectiveRaceBetStatus.REFUNDED:
                    transaction_id = await self._refund_bet(bet=bet)
                    await self._repository.mark_collective_race_bet_paid(
                        bet.id,
                        transaction_id=transaction_id,
                    )
                    total_refunded += bet.stake

        return CollectiveRaceSettlementResult(
            race=settled_race,
            bets=bets,
            winner=settled_race.winner,
            winning_bets=sum(
                1 for bet in bets if bet.status is CollectiveRaceBetStatus.WON
            ),
            lost_bets=sum(
                1 for bet in bets if bet.status is CollectiveRaceBetStatus.LOST
            ),
            refunded_bets=sum(
                1 for bet in bets if bet.status is CollectiveRaceBetStatus.REFUNDED
            ),
            total_paid=total_paid,
            total_refunded=total_refunded,
        )

    async def _pay_bet(self, bet: CollectiveRaceBet) -> int:
        result = await self._economy_repository.mutate_balance(
            guild_id=bet.guild_id,
            user_id=bet.user_id,
            amount=bet.potential_payout,
            transaction_type=EconomyTransactionType.CASINO_PAYOUT,
            actor_id=None,
            reason="collective_race_payout",
            metadata={
                "game": "collective_race",
                "race_id": bet.race_id,
                "bet_id": bet.id,
                "mascot": bet.mascot.value,
                "payout": bet.potential_payout,
            },
        )
        return result.transaction.id

    async def _refund_bet(
        self,
        *,
        bet: CollectiveRaceBet | None,
        guild_id: int | None = None,
        user_id: int | None = None,
        amount: int | None = None,
        race_id: int | None = None,
    ) -> int:
        target_guild_id = bet.guild_id if bet else guild_id
        target_user_id = bet.user_id if bet else user_id
        target_amount = bet.stake if bet else amount
        target_race_id = bet.race_id if bet else race_id
        if target_guild_id is None or target_user_id is None or target_amount is None:
            raise RuntimeError("Dados insuficientes para estornar aposta da corrida.")

        result = await self._economy_repository.mutate_balance(
            guild_id=target_guild_id,
            user_id=target_user_id,
            amount=target_amount,
            transaction_type=EconomyTransactionType.REFUND,
            actor_id=None,
            reason="collective_race_refund",
            metadata={
                "game": "collective_race",
                "race_id": target_race_id,
                "bet_id": bet.id if bet else None,
            },
        )
        return result.transaction.id

    async def _require_race(
        self,
        guild_id: int,
        race_id: int,
    ) -> CollectiveRaceSession:
        race = await self._repository.get_collective_race(race_id)
        if race is None or race.guild_id != guild_id:
            raise CollectiveRaceValidationError("Corrida coletiva nao encontrada.")
        return race

    async def _require_open_race(
        self,
        guild_id: int,
        race_id: int,
    ) -> CollectiveRaceSession:
        race = await self._require_race(guild_id, race_id)
        if race.status.value != "open":
            raise CollectiveRaceValidationError("Esta corrida ja foi encerrada.")
        return race

    def _resolve_winner(self, winner: str | None) -> RaceMascot:
        if winner is not None:
            return self.parse_mascot(winner)
        return self._rng.choice(list(RaceMascot))

    @staticmethod
    def parse_mascot(value: str) -> RaceMascot:
        try:
            return RaceMascot(value.strip().lower())
        except ValueError as exc:
            raise CollectiveRaceValidationError("Mascote invalido.") from exc

    @classmethod
    def _validate_stake(cls, stake: int) -> None:
        if stake < cls.MIN_STAKE:
            raise CollectiveRaceValidationError(f"A aposta minima e {cls.MIN_STAKE}.")
        if stake > cls.MAX_STAKE:
            raise CollectiveRaceValidationError(f"A aposta maxima e {cls.MAX_STAKE}.")

    @classmethod
    def _validate_duration(cls, duration_seconds: int) -> None:
        if duration_seconds < cls.MIN_DURATION_SECONDS:
            raise CollectiveRaceValidationError(
                f"A duracao minima e {cls.MIN_DURATION_SECONDS}s."
            )
        if duration_seconds > cls.MAX_DURATION_SECONDS:
            raise CollectiveRaceValidationError(
                f"A duracao maxima e {cls.MAX_DURATION_SECONDS}s."
            )
