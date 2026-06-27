from __future__ import annotations

import asyncio
import random
from collections.abc import Callable

from app.models.casino import (
    BlackjackCard,
    BlackjackHand,
    BlackjackOutcome,
    BlackjackSession,
    CardRank,
    CardSuit,
)
from app.models.economy import EconomyTransactionType
from app.repositories.economy_repository import SQLiteEconomyRepository


class BlackjackServiceError(Exception):
    """Erro base do BlackJack."""


class BlackjackValidationError(BlackjackServiceError):
    """Erro de validacao de uma acao de BlackJack."""


class BlackjackService:
    """Regras do BlackJack e integracao com a economia."""

    MIN_BET = 1
    MAX_BET = 100_000

    def __init__(
        self,
        repository: SQLiteEconomyRepository,
        *,
        deck_factory: Callable[[], list[BlackjackCard]] | None = None,
    ) -> None:
        self._repository = repository
        self._deck_factory = deck_factory or self._build_shuffled_deck
        self._sessions: dict[tuple[int, int], BlackjackSession] = {}
        self._lock = asyncio.Lock()

    async def start_game(
        self,
        *,
        guild_id: int,
        user_id: int,
        bet: int,
    ) -> BlackjackSession:
        self._validate_bet(bet)
        key = (guild_id, user_id)

        async with self._lock:
            if key in self._sessions:
                raise BlackjackValidationError(
                    "Voce ja possui uma partida de BlackJack em andamento."
                )

            wallet = await self._repository.get_wallet(guild_id, user_id)
            if wallet.balance < bet:
                raise BlackjackValidationError("Saldo insuficiente para essa aposta.")

            await self._debit_bet(guild_id, user_id, bet, reason="blackjack_bet")
            session = BlackjackSession(
                guild_id=guild_id,
                user_id=user_id,
                bet=bet,
                deck=self._deck_factory(),
            )
            self._deal_initial_cards(session)

            if session.player_hand.is_blackjack or session.dealer_hand.is_blackjack:
                await self._resolve_natural_blackjack(session)
                return session

            self._sessions[key] = session
            return session

    async def hit(self, guild_id: int, user_id: int) -> BlackjackSession:
        async with self._lock:
            session = self._get_active_session(guild_id, user_id)
            session.can_double = False
            session.player_hand.add(self._draw(session))

            if session.player_hand.is_bust:
                await self._finish(session, BlackjackOutcome.PLAYER_BUST, payout=0)
            elif session.player_hand.value == 21:
                await self._play_dealer_and_resolve(session)

            return session

    async def stand(self, guild_id: int, user_id: int) -> BlackjackSession:
        async with self._lock:
            session = self._get_active_session(guild_id, user_id)
            session.can_double = False
            await self._play_dealer_and_resolve(session)
            return session

    async def double_down(self, guild_id: int, user_id: int) -> BlackjackSession:
        async with self._lock:
            session = self._get_active_session(guild_id, user_id)
            if not session.can_double or len(session.player_hand.cards) != 2:
                raise BlackjackValidationError(
                    "Voce so pode dobrar antes de pedir cartas."
                )

            wallet = await self._repository.get_wallet(guild_id, user_id)
            if wallet.balance < session.bet:
                raise BlackjackValidationError("Saldo insuficiente para dobrar.")

            await self._debit_bet(
                guild_id,
                user_id,
                session.bet,
                reason="blackjack_double",
            )
            session.bet *= 2
            session.can_double = False
            session.player_hand.add(self._draw(session))

            if session.player_hand.is_bust:
                await self._finish(session, BlackjackOutcome.PLAYER_BUST, payout=0)
            else:
                await self._play_dealer_and_resolve(session)

            return session

    async def expire_game(self, guild_id: int, user_id: int) -> BlackjackSession | None:
        async with self._lock:
            session = self._sessions.get((guild_id, user_id))
            if session is None:
                return None

            await self._finish(session, BlackjackOutcome.EXPIRED, payout=0)
            return session

    def has_active_session(self, guild_id: int, user_id: int) -> bool:
        return (guild_id, user_id) in self._sessions

    async def _resolve_natural_blackjack(self, session: BlackjackSession) -> None:
        if session.player_hand.is_blackjack and session.dealer_hand.is_blackjack:
            await self._finish(session, BlackjackOutcome.PUSH, payout=session.bet)
            return
        if session.player_hand.is_blackjack:
            await self._finish(
                session,
                BlackjackOutcome.PLAYER_BLACKJACK,
                payout=(session.bet * 5) // 2,
            )
            return
        await self._finish(session, BlackjackOutcome.DEALER_BLACKJACK, payout=0)

    async def _play_dealer_and_resolve(self, session: BlackjackSession) -> None:
        while session.dealer_hand.value < 17:
            session.dealer_hand.add(self._draw(session))

        if session.dealer_hand.is_bust:
            await self._finish(
                session,
                BlackjackOutcome.PLAYER_WIN,
                payout=session.bet * 2,
            )
            return

        player_value = session.player_hand.value
        dealer_value = session.dealer_hand.value
        if player_value > dealer_value:
            await self._finish(
                session,
                BlackjackOutcome.PLAYER_WIN,
                payout=session.bet * 2,
            )
        elif player_value == dealer_value:
            await self._finish(session, BlackjackOutcome.PUSH, payout=session.bet)
        else:
            await self._finish(session, BlackjackOutcome.DEALER_WIN, payout=0)

    async def _finish(
        self,
        session: BlackjackSession,
        outcome: BlackjackOutcome,
        *,
        payout: int,
    ) -> None:
        session.outcome = outcome
        session.payout = payout
        self._sessions.pop((session.guild_id, session.user_id), None)

        if payout <= 0:
            return

        await self._repository.mutate_balance(
            guild_id=session.guild_id,
            user_id=session.user_id,
            amount=payout,
            transaction_type=EconomyTransactionType.CASINO_PAYOUT,
            actor_id=None,
            reason="blackjack_payout",
            metadata={
                "game": "blackjack",
                "bet": session.bet,
                "outcome": outcome.value,
            },
        )

    async def _debit_bet(
        self,
        guild_id: int,
        user_id: int,
        amount: int,
        *,
        reason: str,
    ) -> None:
        try:
            await self._repository.mutate_balance(
                guild_id=guild_id,
                user_id=user_id,
                amount=-amount,
                transaction_type=EconomyTransactionType.CASINO_BET,
                actor_id=None,
                reason=reason,
                metadata={"game": "blackjack"},
            )
        except ValueError as exc:
            raise BlackjackValidationError(
                "Saldo insuficiente para essa aposta."
            ) from exc

    def _deal_initial_cards(self, session: BlackjackSession) -> None:
        session.player_hand.add(self._draw(session))
        session.dealer_hand.add(self._draw(session))
        session.player_hand.add(self._draw(session))

    def _get_active_session(self, guild_id: int, user_id: int) -> BlackjackSession:
        session = self._sessions.get((guild_id, user_id))
        if session is None:
            raise BlackjackValidationError(
                "Voce nao possui uma partida de BlackJack em andamento."
            )
        return session

    @staticmethod
    def _draw(session: BlackjackSession) -> BlackjackCard:
        if not session.deck:
            session.deck.extend(BlackjackService._build_shuffled_deck())
        return session.deck.pop(0)

    @classmethod
    def _build_shuffled_deck(cls) -> list[BlackjackCard]:
        deck = [
            BlackjackCard(rank=rank, suit=suit)
            for suit in CardSuit
            for rank in CardRank
        ]
        random.SystemRandom().shuffle(deck)
        return deck

    @classmethod
    def _validate_bet(cls, bet: int) -> None:
        if bet < cls.MIN_BET:
            raise BlackjackValidationError(
                f"A aposta minima e de {cls.MIN_BET} ponto(s)."
            )
        if bet > cls.MAX_BET:
            raise BlackjackValidationError(
                f"A aposta maxima e de {cls.MAX_BET} ponto(s)."
            )


def calculate_hand_value(cards: list[BlackjackCard]) -> int:
    """Calcula a pontuacao de uma lista de cartas."""

    return BlackjackHand(cards=list(cards)).value
