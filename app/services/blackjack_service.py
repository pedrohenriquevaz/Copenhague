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
from app.repositories.economy_protocol import EconomyRepositoryProtocol
from app.services.economic_tier_service import EconomicTierService
from app.services.economy_limits import (
    EconomicDifficultyDecision,
    EconomicDifficultyPolicyService,
)
from app.services.game_progress_service import GameProgressService


class BlackjackServiceError(Exception):
    """Erro base do BlackJack."""


class BlackjackValidationError(BlackjackServiceError):
    """Erro de validacao de uma acao de BlackJack."""


class BlackjackService:
    """Regras do BlackJack e integracao com a economia."""

    MIN_BET = 1
    STREAK_BONUS_PER_WIN_PERCENT = 10
    MAX_STREAK_BONUS_PERCENT = 50

    def __init__(
        self,
        repository: EconomyRepositoryProtocol,
        *,
        progress_service: GameProgressService | None = None,
        deck_factory: Callable[[], list[BlackjackCard]] | None = None,
        economic_policy: EconomicDifficultyPolicyService | None = None,
    ) -> None:
        self._repository = repository
        self._progress_service = progress_service
        self._deck_factory = deck_factory or self._build_shuffled_deck
        self._economic_policy = economic_policy or EconomicDifficultyPolicyService(
            repository, EconomicTierService()
        )
        self._sessions: dict[tuple[int, int], BlackjackSession] = {}
        self._economic_decisions: dict[tuple[int, int], EconomicDifficultyDecision] = {}
        self._win_streaks: dict[tuple[int, int], int] = {}
        self._lock = asyncio.Lock()

    async def start_game(
        self,
        *,
        guild_id: int,
        user_id: int,
        bet: int,
    ) -> BlackjackSession:
        settings = await self._repository.get_guild_settings(guild_id)
        self._validate_bet(
            bet,
            settings.casino_min_bet_blackjack,
            settings.casino_max_bet,
        )
        economic_decision = await self._economic_policy.select(
            settings,
            guild_id=guild_id,
            user_id=user_id,
            game="blackjack",
        )
        self._raise_if_profit_limit_reached(economic_decision)
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
            self._economic_decisions[key] = economic_decision
            session = BlackjackSession(
                guild_id=guild_id,
                user_id=user_id,
                bet=bet,
                deck=self._deck_factory(),
            )
            self._deal_initial_cards(session)
            await self._unlock_blackjack_start_progress(guild_id, user_id)

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

            settings = await self._repository.get_guild_settings(guild_id)
            self._validate_bet(
                session.bet * 2,
                settings.casino_min_bet_blackjack,
                settings.casino_max_bet,
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

    async def reset_user_state(self, guild_id: int, user_id: int) -> None:
        async with self._lock:
            key = (guild_id, user_id)
            self._sessions.pop(key, None)
            self._economic_decisions.pop(key, None)
            self._win_streaks.pop(key, None)

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
        key = (session.guild_id, session.user_id)
        session.base_payout = payout
        if self._is_player_win(outcome):
            session.win_streak = self._win_streaks.get(key, 0) + 1
            session.payout_multiplier_percent = self._streak_multiplier_percent(
                session.win_streak
            )
            session.streak_bonus = self._calculate_streak_bonus(
                bet=session.bet,
                payout=payout,
                multiplier_percent=session.payout_multiplier_percent,
            )
            payout += session.streak_bonus
            self._win_streaks[key] = session.win_streak
        else:
            session.win_streak = 0
            session.payout_multiplier_percent = 100
            session.streak_bonus = 0
            self._win_streaks.pop(key, None)

        session.outcome = outcome
        self._sessions.pop(key, None)
        economic_decision = self._economic_decisions.pop(key)

        if payout > 0:
            settlement = await self._economic_policy.settle_payout(
                economic_decision,
                guild_id=session.guild_id,
                user_id=session.user_id,
                stake=session.bet,
                payout=payout,
                transaction_type=EconomyTransactionType.CASINO_PAYOUT,
                reason="blackjack_payout",
                metadata={
                    "game": "blackjack",
                    "bet": session.bet,
                    "outcome": outcome.value,
                    "base_payout": session.base_payout,
                    "streak_bonus": session.streak_bonus,
                    "win_streak": session.win_streak,
                    "payout_multiplier_percent": session.payout_multiplier_percent,
                },
            )
            payout = settlement.paid_payout
        session.payout = payout
        credit = await self._repository.apply_credit_protection(
            guild_id=session.guild_id,
            user_id=session.user_id,
            game_key="blackjack",
            stake=session.bet,
            is_loss=outcome
            in {
                BlackjackOutcome.DEALER_BLACKJACK,
                BlackjackOutcome.DEALER_WIN,
                BlackjackOutcome.EXPIRED,
                BlackjackOutcome.PLAYER_BUST,
            },
            metadata={
                "source": "blackjack",
                "outcome": outcome.value,
                "bet": session.bet,
            },
        )
        session.cashback = credit.cashback_amount
        await self._unlock_blackjack_finish_progress(session)

    async def _unlock_blackjack_start_progress(
        self,
        guild_id: int,
        user_id: int,
    ) -> None:
        if self._progress_service is None:
            return
        await self._progress_service.unlock(guild_id, user_id, "first_bet")
        await self._progress_service.unlock(guild_id, user_id, "first_blackjack")
        await self._progress_service.evaluate_user_milestones(guild_id, user_id)

    async def _unlock_blackjack_finish_progress(
        self,
        session: BlackjackSession,
    ) -> None:
        if self._progress_service is None or session.outcome is None:
            return
        if self._is_player_win(session.outcome):
            await self._progress_service.unlock(
                session.guild_id,
                session.user_id,
                "first_win",
            )
            if session.win_streak >= 3:
                await self._progress_service.unlock(
                    session.guild_id,
                    session.user_id,
                    "blackjack_streak_3",
                )
        elif session.outcome in {
            BlackjackOutcome.DEALER_BLACKJACK,
            BlackjackOutcome.DEALER_WIN,
            BlackjackOutcome.EXPIRED,
            BlackjackOutcome.PLAYER_BUST,
        }:
            await self._progress_service.unlock(
                session.guild_id,
                session.user_id,
                "first_loss",
            )
        await self._progress_service.evaluate_user_milestones(
            session.guild_id,
            session.user_id,
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
                "Voce não possui uma partida de BlackJack em andamento."
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
    def _validate_bet(cls, bet: int, min_bet: int, max_bet: int) -> None:
        if bet < min_bet:
            raise BlackjackValidationError(f"A aposta mínima e de {min_bet} ponto(s).")
        if bet > max_bet:
            raise BlackjackValidationError(f"A aposta máxima e de {max_bet} ponto(s).")

    @staticmethod
    def _raise_if_profit_limit_reached(
        decision: EconomicDifficultyDecision,
    ) -> None:
        if (
            decision.profit_cap_applies
            and decision.daily_profit >= decision.daily_limit
        ):
            raise BlackjackValidationError(
                "Voce atingiu o teto diário de lucro dos jogos."
            )

    @staticmethod
    def _is_player_win(outcome: BlackjackOutcome) -> bool:
        return outcome in {
            BlackjackOutcome.PLAYER_BLACKJACK,
            BlackjackOutcome.PLAYER_WIN,
        }

    @classmethod
    def _streak_multiplier_percent(cls, win_streak: int) -> int:
        bonus = max(0, win_streak - 1) * cls.STREAK_BONUS_PER_WIN_PERCENT
        capped_bonus = min(bonus, cls.MAX_STREAK_BONUS_PERCENT)
        return 100 + capped_bonus

    @staticmethod
    def _calculate_streak_bonus(
        *,
        bet: int,
        payout: int,
        multiplier_percent: int,
    ) -> int:
        profit = max(0, payout - bet)
        bonus_percent = max(0, multiplier_percent - 100)
        return (profit * bonus_percent) // 100


def calculate_hand_value(cards: list[BlackjackCard]) -> int:
    """Calcula a pontuacao de uma lista de cartas."""

    return BlackjackHand(cards=list(cards)).value
