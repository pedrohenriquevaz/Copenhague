from __future__ import annotations

import asyncio
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.models.economy import EconomyTransactionType
from app.models.giveaway import utc_now
from app.models.match_bet import (
    MatchBetCreate,
    MatchBetMatch,
    MatchBetPlacementResult,
    MatchBetSettlementResult,
    MatchBetTeam,
    MatchBetTicket,
    MatchBetTicketCreate,
    MatchBetTicketStatus,
)
from app.repositories.economy_protocol import EconomyRepositoryProtocol
from app.repositories.match_bet_repository import MatchBetRepositoryProtocol
from app.services.economic_tier_service import EconomicTierService
from app.services.economy_limits import EconomicDifficultyPolicyService


class MatchBetServiceError(Exception):
    """Erro base do sistema de bets de partidas."""


class MatchBetValidationError(MatchBetServiceError):
    """Erro de validacao das bets de partidas."""


class MatchBetService:
    """Regras de negocio para apostas saudaveis em campeonatos."""

    MIN_STAKE = 1
    MIN_ODD_BPS = 101
    MAX_ODD_BPS = 10_000

    def __init__(
        self,
        repository: MatchBetRepositoryProtocol,
        economy_repository: EconomyRepositoryProtocol,
        *,
        economic_policy: EconomicDifficultyPolicyService | None = None,
    ) -> None:
        self._repository = repository
        self._economy_repository = economy_repository
        self._economic_policy = economic_policy or EconomicDifficultyPolicyService(
            economy_repository, EconomicTierService()
        )
        self._lock = asyncio.Lock()

    async def create_match(
        self,
        *,
        guild_id: int,
        title: str,
        team_1: str,
        team_2: str,
        odd_team_1: float | str,
        odd_team_2: float | str,
        created_by: int,
    ) -> MatchBetMatch:
        title = self._require_text(title, "O titulo da partida nao pode ficar vazio.")
        team_1 = self._require_text(team_1, "O time 1 nao pode ficar vazio.")
        team_2 = self._require_text(team_2, "O time 2 nao pode ficar vazio.")
        if team_1.casefold() == team_2.casefold():
            raise MatchBetValidationError("Os times precisam ser diferentes.")

        return await self._repository.create_match(
            MatchBetCreate(
                guild_id=guild_id,
                title=title,
                team_1=team_1,
                team_2=team_2,
                odd_team_1_bps=self.parse_odd_bps(odd_team_1),
                odd_team_2_bps=self.parse_odd_bps(odd_team_2),
                created_by=created_by,
                created_at=utc_now(),
            )
        )

    async def publish_match(
        self,
        match_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> MatchBetMatch:
        return await self._repository.publish_match(
            match_id,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def get_match(self, match_id: int) -> MatchBetMatch | None:
        return await self._repository.get_match(match_id)

    async def get_match_by_message_id(
        self,
        message_id: int,
    ) -> MatchBetMatch | None:
        return await self._repository.get_match_by_message_id(message_id)

    async def list_active_matches(self, guild_id: int) -> list[MatchBetMatch]:
        return await self._repository.list_active_matches(guild_id)

    async def place_bet(
        self,
        *,
        guild_id: int,
        user_id: int,
        match_id: int,
        team: str,
        stake: int,
    ) -> MatchBetPlacementResult:
        selected_team = self.parse_team(team)
        settings = await self._economy_repository.get_guild_settings(guild_id)
        self._validate_stake(
            stake,
            settings.casino_min_bet_match_bet,
            settings.casino_max_bet,
        )

        async with self._lock:
            match = await self._require_open_match(guild_id, match_id)
            team_name = self.team_name(match, selected_team)
            odd_bps = self.team_odd_bps(match, selected_team)
            potential_payout = self.calculate_payout(stake, odd_bps)
            economic_decision = await self._economic_policy.select(
                settings,
                guild_id=guild_id,
                user_id=user_id,
                game="match_bet",
            )

            try:
                debit = await self._economy_repository.mutate_balance(
                    guild_id=guild_id,
                    user_id=user_id,
                    amount=-stake,
                    transaction_type=EconomyTransactionType.MATCH_BET,
                    actor_id=None,
                    reason="match_bet_stake",
                    metadata={
                        "match_id": match.id,
                        "team": selected_team.value,
                        "team_name": team_name,
                        "odd": self.format_odd_bps(odd_bps),
                        "potential_payout": potential_payout,
                    },
                )
            except ValueError as exc:
                raise MatchBetValidationError(
                    "Saldo insuficiente para essa aposta."
                ) from exc

            try:
                ticket = await self._repository.create_ticket(
                    MatchBetTicketCreate(
                        match_id=match.id,
                        guild_id=guild_id,
                        user_id=user_id,
                        team=selected_team,
                        team_name_snapshot=team_name,
                        stake=stake,
                        odd_bps=odd_bps,
                        potential_payout=potential_payout,
                        debit_transaction_id=debit.transaction.id,
                        economic_policy_snapshot=self._economic_policy.snapshot(
                            economic_decision
                        ),
                        created_at=utc_now(),
                    )
                )
            except ValueError as exc:
                await self._refund_stake(
                    guild_id=guild_id,
                    user_id=user_id,
                    amount=stake,
                    match_id=match.id,
                    ticket_id=None,
                    reason="match_bet_failed_refund",
                    idempotency_key=(
                        f"match_bet:transaction:{debit.transaction.id}:refund"
                    ),
                )
                raise MatchBetValidationError(str(exc)) from exc
            except Exception:
                await self._refund_stake(
                    guild_id=guild_id,
                    user_id=user_id,
                    amount=stake,
                    match_id=match.id,
                    ticket_id=None,
                    reason="match_bet_failed_refund",
                    idempotency_key=(
                        f"match_bet:transaction:{debit.transaction.id}:refund"
                    ),
                )
                raise

        wallet = await self._economy_repository.get_wallet(guild_id, user_id)
        return MatchBetPlacementResult(match=match, ticket=ticket, wallet=wallet)

    async def update_odds(
        self,
        *,
        guild_id: int,
        match_id: int,
        odd_team_1: float | str,
        odd_team_2: float | str,
    ) -> MatchBetMatch:
        current = await self._require_match(guild_id, match_id)
        if not current.is_active:
            raise MatchBetValidationError("Esta partida ja foi encerrada.")

        updated = await self._repository.update_odds(
            match_id,
            odd_team_1_bps=self.parse_odd_bps(odd_team_1),
            odd_team_2_bps=self.parse_odd_bps(odd_team_2),
        )
        if updated is None:
            raise MatchBetValidationError("Nao encontrei essa partida de apostas.")
        if not updated.is_active:
            raise MatchBetValidationError("Esta partida ja foi encerrada.")
        return updated

    async def settle_match(
        self,
        *,
        guild_id: int,
        match_id: int,
        winner: str,
    ) -> MatchBetSettlementResult:
        winning_team = None if winner == "cancelar" else self.parse_team(winner)

        async with self._lock:
            match = await self._require_match(guild_id, match_id)
            if not match.is_active and match.resolved_winner is not winning_team:
                raise MatchBetValidationError(
                    "Esta partida ja foi encerrada com outro resultado."
                )

            settled_match, tickets = await self._repository.settle_match(
                match_id,
                winner=winning_team,
            )
            if settled_match is None:
                raise MatchBetValidationError("Nao encontrei essa partida de apostas.")

            total_paid = 0
            total_refunded = 0
            total_cashback = 0
            for ticket in tickets:
                if ticket.status is MatchBetTicketStatus.WON:
                    paid_amount = 0
                    if ticket.payout_transaction_id is None:
                        transaction_id, paid_amount = await self._pay_ticket(ticket)
                        await self._repository.mark_ticket_paid(
                            ticket.id,
                            transaction_id=transaction_id,
                        )
                    total_paid += paid_amount
                    await self._economy_repository.apply_credit_protection(
                        guild_id=ticket.guild_id,
                        user_id=ticket.user_id,
                        game_key="match_bet",
                        stake=ticket.stake,
                        is_loss=False,
                        metadata={
                            "source": "match_bet",
                            "match_id": ticket.match_id,
                            "ticket_id": ticket.id,
                        },
                        idempotency_key=f"match_bet:{ticket.id}:credit",
                    )
                elif ticket.status is MatchBetTicketStatus.LOST:
                    credit = await self._economy_repository.apply_credit_protection(
                        guild_id=ticket.guild_id,
                        user_id=ticket.user_id,
                        game_key="match_bet",
                        stake=ticket.stake,
                        is_loss=True,
                        metadata={
                            "source": "match_bet",
                            "match_id": ticket.match_id,
                            "ticket_id": ticket.id,
                            "team": ticket.team.value,
                        },
                        idempotency_key=f"match_bet:{ticket.id}:credit",
                    )
                    total_cashback += credit.cashback_amount
                elif ticket.status is MatchBetTicketStatus.REFUNDED:
                    if ticket.payout_transaction_id is not None:
                        continue
                    transaction_id = await self._refund_stake(
                        guild_id=ticket.guild_id,
                        user_id=ticket.user_id,
                        amount=ticket.stake,
                        match_id=ticket.match_id,
                        ticket_id=ticket.id,
                        reason="match_bet_cancel_refund",
                        idempotency_key=f"match_bet:{ticket.id}:refund",
                    )
                    await self._repository.mark_ticket_paid(
                        ticket.id,
                        transaction_id=transaction_id,
                    )
                    total_refunded += ticket.stake

        return MatchBetSettlementResult(
            match=settled_match,
            tickets=tickets,
            winning_tickets=sum(
                1 for ticket in tickets if ticket.status is MatchBetTicketStatus.WON
            ),
            lost_tickets=sum(
                1 for ticket in tickets if ticket.status is MatchBetTicketStatus.LOST
            ),
            refunded_tickets=sum(
                1
                for ticket in tickets
                if ticket.status is MatchBetTicketStatus.REFUNDED
            ),
            total_paid=total_paid,
            total_refunded=total_refunded,
            total_cashback=total_cashback,
        )

    async def _pay_ticket(self, ticket: MatchBetTicket) -> tuple[int, int]:
        settings = await self._economy_repository.get_guild_settings(ticket.guild_id)
        decision = await self._economic_policy.decision_for_settlement(
            ticket.economic_policy_snapshot,
            settings,
            guild_id=ticket.guild_id,
            user_id=ticket.user_id,
            game="match_bet",
            stake=ticket.stake,
        )
        settlement = await self._economic_policy.settle_payout(
            decision,
            guild_id=ticket.guild_id,
            user_id=ticket.user_id,
            stake=ticket.stake,
            payout=ticket.potential_payout,
            transaction_type=EconomyTransactionType.MATCH_BET_PAYOUT,
            reason="match_bet_payout",
            metadata={
                "game": "match_bet",
                "match_id": ticket.match_id,
                "ticket_id": ticket.id,
                "team": ticket.team.value,
                "odd": self.format_odd_bps(ticket.odd_bps),
                "stake": ticket.stake,
                "payout": ticket.potential_payout,
                "uncapped_payout": ticket.potential_payout,
            },
            idempotency_key=f"match_bet:{ticket.id}",
        )
        return settlement.transaction.id, settlement.paid_payout

    async def _refund_stake(
        self,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
        match_id: int,
        ticket_id: int | None,
        reason: str,
        idempotency_key: str | None = None,
    ) -> int:
        result = await self._economy_repository.mutate_balance(
            guild_id=guild_id,
            user_id=user_id,
            amount=amount,
            transaction_type=EconomyTransactionType.REFUND,
            actor_id=None,
            reason=reason,
            metadata={
                "match_id": match_id,
                "ticket_id": ticket_id,
                "source": "match_bet",
            },
            idempotency_key=idempotency_key,
        )
        return result.transaction.id

    async def _require_match(
        self,
        guild_id: int,
        match_id: int,
    ) -> MatchBetMatch:
        match = await self._repository.get_match(match_id)
        if match is None or match.guild_id != guild_id:
            raise MatchBetValidationError("Nao encontrei essa partida de apostas.")
        return match

    async def _require_open_match(
        self,
        guild_id: int,
        match_id: int,
    ) -> MatchBetMatch:
        match = await self._require_match(guild_id, match_id)
        if not match.is_active:
            raise MatchBetValidationError("Esta partida nao aceita novas apostas.")
        return match

    @classmethod
    def parse_odd_bps(cls, value: float | str) -> int:
        try:
            decimal = Decimal(str(value).replace(",", "."))
        except InvalidOperation as exc:
            raise MatchBetValidationError("Odd invalida.") from exc

        bps = int((decimal * Decimal("100")).quantize(Decimal("1"), ROUND_HALF_UP))
        if bps < cls.MIN_ODD_BPS:
            raise MatchBetValidationError("A odd minima aceita e 1.01.")
        if bps > cls.MAX_ODD_BPS:
            raise MatchBetValidationError("A odd maxima aceita e 100.00.")
        return bps

    @staticmethod
    def format_odd_bps(odd_bps: int) -> str:
        return f"{odd_bps / 100:.2f}"

    @staticmethod
    def calculate_payout(stake: int, odd_bps: int) -> int:
        return max(stake, stake * odd_bps // 100)

    @staticmethod
    def parse_team(value: str) -> MatchBetTeam:
        try:
            return MatchBetTeam(value)
        except ValueError as exc:
            raise MatchBetValidationError("Time invalido para essa aposta.") from exc

    @staticmethod
    def team_name(match: MatchBetMatch, team: MatchBetTeam) -> str:
        if team is MatchBetTeam.TEAM_1:
            return match.team_1
        return match.team_2

    @staticmethod
    def team_odd_bps(match: MatchBetMatch, team: MatchBetTeam) -> int:
        if team is MatchBetTeam.TEAM_1:
            return match.odd_team_1_bps
        return match.odd_team_2_bps

    @classmethod
    def _validate_stake(cls, stake: int, min_stake: int, max_stake: int) -> None:
        if stake < min_stake:
            raise MatchBetValidationError(f"A aposta minima e {min_stake}.")
        if stake > max_stake:
            raise MatchBetValidationError(f"A aposta maxima e {max_stake}.")

    @staticmethod
    def _require_text(value: str, message: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise MatchBetValidationError(message)
        return normalized
