from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from app.models.economy import EconomyTransactionType, UserWallet
from app.models.giveaway import utc_now
from app.models.truco import (
    TRUCO_RANK_ORDER,
    TRUCO_SUIT_POWER,
    TRUCO_VALUES,
    TrucoActionType,
    TrucoCard,
    TrucoChallenge,
    TrucoGameMode,
    TrucoGameStatus,
    TrucoPlayedCard,
    TrucoPlayer,
    TrucoRank,
    TrucoRoundReveal,
    TrucoSession,
    TrucoSuit,
    TrucoTeam,
)
from app.repositories.economy_protocol import EconomyRepositoryProtocol
from app.repositories.truco_repository import TrucoRepositoryProtocol
from app.services.economic_tier_service import EconomicTierService
from app.services.economy_limits import (
    EconomicDifficultyPolicyService,
)
from app.services.game_progress_service import GameProgressService


class TrucoServiceError(Exception):
    """Erro base do Truco."""


class TrucoValidationError(TrucoServiceError):
    """Erro de validação de uma ação de Truco."""


@dataclass(slots=True)
class TrucoFinancialResult:
    payouts: dict[int, int]
    wallets: dict[int, UserWallet]
    total_paid: int = 0
    total_refunded: int = 0
    total_cashback: int = 0


class TrucoService:
    """Regras do Truco Paulista 2x2 e integração com a economia."""

    MIN_STAKE = 1
    WINNING_SCORE = 12
    PLAYER_COUNT = 4
    MACHINE_USER_ID = -1

    def __init__(
        self,
        repository: TrucoRepositoryProtocol,
        economy_repository: EconomyRepositoryProtocol,
        *,
        progress_service: GameProgressService | None = None,
        rng: random.Random | random.SystemRandom | None = None,
        economic_policy: EconomicDifficultyPolicyService | None = None,
    ) -> None:
        self._repository = repository
        self._economy_repository = economy_repository
        self._progress_service = progress_service
        self._rng = rng or random.SystemRandom()
        self._economic_policy = economic_policy or EconomicDifficultyPolicyService(
            economy_repository, EconomicTierService()
        )
        self._lock = asyncio.Lock()

    async def create_lobby(
        self,
        *,
        guild_id: int,
        channel_id: int,
        created_by: int,
        partner_id: int,
        opponent_1_id: int,
        opponent_2_id: int,
        stake: int,
    ) -> TrucoSession:
        player_ids = [created_by, opponent_1_id, partner_id, opponent_2_id]
        if len(set(player_ids)) != self.PLAYER_COUNT:
            raise TrucoValidationError("Os quatro participantes precisam ser únicos.")

        settings = await self._economy_repository.get_guild_settings(guild_id)
        self._validate_stake(
            stake,
            settings.casino_min_bet_truco,
            settings.casino_max_bet,
        )
        for user_id in player_ids:
            await self._validate_daily_profit_limit(guild_id, user_id)
            wallet = await self._economy_repository.get_wallet(guild_id, user_id)
            if wallet.balance < stake:
                raise TrucoValidationError(
                    f"<@{user_id}> não possui saldo suficiente para a aposta."
                )
            active_games = await self._repository.list_active_games_for_user(
                guild_id,
                user_id,
            )
            if active_games:
                raise TrucoValidationError(
                    f"<@{user_id}> já participa de uma partida de Truco ativa."
                )

        session = TrucoSession(
            id=None,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=None,
            created_by=created_by,
            stake=stake,
            status=TrucoGameStatus.LOBBY,
            players=[
                TrucoPlayer(created_by, TrucoTeam.BLUE, 0),
                TrucoPlayer(opponent_1_id, TrucoTeam.RED, 1),
                TrucoPlayer(partner_id, TrucoTeam.BLUE, 2),
                TrucoPlayer(opponent_2_id, TrucoTeam.RED, 3),
            ],
        )
        created = await self._repository.create_game(session)
        await self._record(created, created_by, TrucoActionType.CREATE)
        return created

    async def create_pve_game(
        self,
        *,
        guild_id: int,
        channel_id: int,
        created_by: int,
        stake: int,
    ) -> TrucoSession:
        settings = await self._economy_repository.get_guild_settings(guild_id)
        self._validate_stake(
            stake,
            settings.casino_min_bet_truco,
            settings.casino_max_bet,
        )
        await self._validate_daily_profit_limit(guild_id, created_by)
        wallet = await self._economy_repository.get_wallet(guild_id, created_by)
        if wallet.balance < stake:
            raise TrucoValidationError(
                "Você não possui saldo suficiente para a aposta."
            )
        if await self._repository.list_active_games_for_user(guild_id, created_by):
            raise TrucoValidationError(
                "Você já participa de uma partida de Truco ativa."
            )
        async with self._lock:
            session = TrucoSession(
                id=None,
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=None,
                created_by=created_by,
                stake=stake,
                status=TrucoGameStatus.LOBBY,
                players=[
                    TrucoPlayer(created_by, TrucoTeam.BLUE, 0, accepted=True),
                    TrucoPlayer(
                        self.MACHINE_USER_ID,
                        TrucoTeam.RED,
                        1,
                        accepted=True,
                        is_bot=True,
                    ),
                ],
                game_mode=TrucoGameMode.PVE,
            )
            session = await self._repository.create_game(session)
            await self._record(session, created_by, TrucoActionType.CREATE)
            await self._start_game(session)
            await self._record(session, created_by, TrucoActionType.START)
            return await self._repository.update_game(session)

    async def attach_message(self, game_id: int, message_id: int) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            session.message_id = message_id
            return await self._repository.update_game(session)

    async def accept_lobby(self, game_id: int, user_id: int) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_status(session, TrucoGameStatus.LOBBY)
            player = self._require_player(session, user_id)
            player.accepted = True
            await self._record(session, user_id, TrucoActionType.ACCEPT)
            if session.all_accepted:
                await self._start_game(session)
                await self._record(session, user_id, TrucoActionType.START)
            return await self._repository.update_game(session)

    async def decline_lobby(self, game_id: int, user_id: int) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_status(session, TrucoGameStatus.LOBBY)
            self._require_player(session, user_id)
            session.status = TrucoGameStatus.CANCELLED
            session.finished_at = utc_now()
            await self._record(session, user_id, TrucoActionType.DECLINE)
            return await self._repository.update_game(session)

    async def cancel_game(self, game_id: int, user_id: int) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            if user_id != session.created_by:
                raise TrucoValidationError(
                    "Apenas quem criou a mesa pode cancelar a partida."
                )
            if session.status is TrucoGameStatus.FINISHED:
                raise TrucoValidationError("Esta partida já foi finalizada.")
            if session.status is TrucoGameStatus.PLAYING:
                await self._refund_all(session)
            session.status = TrucoGameStatus.CANCELLED
            session.finished_at = utc_now()
            await self._record(session, user_id, TrucoActionType.CANCEL)
            return await self._repository.update_game(session)

    async def force_cancel_active_games(
        self,
        *,
        guild_id: int,
        target_user_id: int,
        actor_id: int,
        reason: str,
    ) -> list[TrucoSession]:
        """Cancela administrativamente todas as mesas ativas de um usuário."""

        clean_reason = reason.strip()
        if not clean_reason:
            raise TrucoValidationError("Informe o motivo do cancelamento.")

        async with self._lock:
            games = await self._repository.list_active_games_for_user(
                guild_id,
                target_user_id,
            )
            if not games:
                raise TrucoValidationError(
                    "Este usuário não participa de uma partida de Truco ativa."
                )

            cancelled: list[TrucoSession] = []
            for session in games:
                refunded = session.status is TrucoGameStatus.PLAYING
                if refunded:
                    await self._refund_all(session)
                session.status = TrucoGameStatus.CANCELLED
                session.finished_at = utc_now()
                await self._record(
                    session,
                    actor_id,
                    TrucoActionType.CANCEL,
                    {
                        "forced": True,
                        "target_user_id": target_user_id,
                        "reason": clean_reason[:500],
                        "stakes_refunded": refunded,
                    },
                )
                cancelled.append(await self._repository.update_game(session))
            return cancelled

    async def play_card(
        self,
        *,
        game_id: int,
        user_id: int,
        card_index: int,
        closed: bool = False,
    ) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_playing(session)
            self._require_reveal_complete(session)
            player = self._require_player(session, user_id)
            if session.pending_challenge is not None:
                raise TrucoValidationError(
                    "Existe um pedido de Truco pendente. Resolva antes de jogar."
                )
            if session.current_turn_user_id != user_id:
                raise TrucoValidationError("Ainda não é sua vez de jogar.")
            if closed and session.round_number not in {1, 3}:
                raise TrucoValidationError(
                    "Carta fechada só pode ser usada na primeira ou terceira rodada."
                )

            hand = session.hands.get(user_id, [])
            if card_index < 0 or card_index >= len(hand):
                raise TrucoValidationError("Essa carta não está disponível.")
            card = hand.pop(card_index)
            played = TrucoPlayedCard(
                user_id=user_id,
                card=card,
                round_number=session.round_number,
                play_order=len(self._round_cards(session)) + 1,
                is_closed=closed,
                played_at=utc_now(),
            )
            session.played_cards.append(played)
            await self._record(
                session,
                user_id,
                TrucoActionType.PLAY_CARD,
                {
                    "card": card.code,
                    "closed": closed,
                    "round": session.round_number,
                },
            )
            if len(self._round_cards(session)) >= len(session.players):
                await self._finish_round(session)
            else:
                session.current_turn_user_id = self._next_turn_user_id(
                    session,
                    player.seat_position,
                )
            return await self._repository.update_game(session)

    async def request_truco(self, game_id: int, user_id: int) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_playing(session)
            self._require_reveal_complete(session)
            player = self._require_player(session, user_id)
            if session.pending_challenge is not None:
                raise TrucoValidationError("Já existe um pedido de Truco pendente.")
            if session.hand_value >= TRUCO_VALUES[-1]:
                raise TrucoValidationError("A mão já está valendo 12.")
            if self._is_hand_of_eleven(session):
                raise TrucoValidationError("Não é permitido trucar na mão de 11.")
            proposed = self._next_truco_value(session.hand_value)
            session.pending_challenge = TrucoChallenge(
                requested_by=user_id,
                requesting_team=player.team,
                target_team=player.team.opponent,
                current_value=session.hand_value,
                proposed_value=proposed,
            )
            await self._record(
                session,
                user_id,
                TrucoActionType.REQUEST_TRUCO,
                {"from": session.hand_value, "to": proposed},
            )
            return await self._repository.update_game(session)

    async def accept_truco(self, game_id: int, user_id: int) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_reveal_complete(session)
            challenge = self._require_challenge_response(session, user_id)
            session.hand_value = challenge.proposed_value
            session.pending_challenge = None
            await self._record(
                session,
                user_id,
                TrucoActionType.ACCEPT_TRUCO,
                {"value": session.hand_value},
            )
            return await self._repository.update_game(session)

    async def raise_truco(self, game_id: int, user_id: int) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_reveal_complete(session)
            challenge = self._require_challenge_response(session, user_id)
            if challenge.proposed_value >= TRUCO_VALUES[-1]:
                raise TrucoValidationError("Não é possível pedir mais que 12.")
            proposed = self._next_truco_value(challenge.proposed_value)
            player = self._require_player(session, user_id)
            session.pending_challenge = TrucoChallenge(
                requested_by=user_id,
                requesting_team=player.team,
                target_team=player.team.opponent,
                current_value=challenge.proposed_value,
                proposed_value=proposed,
            )
            await self._record(
                session,
                user_id,
                TrucoActionType.RAISE_TRUCO,
                {"from": challenge.proposed_value, "to": proposed},
            )
            return await self._repository.update_game(session)

    async def run(self, game_id: int, user_id: int) -> TrucoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_playing(session)
            self._require_reveal_complete(session)
            player = self._require_player(session, user_id)
            if session.pending_challenge is not None:
                challenge = self._require_challenge_response(session, user_id)
                winner = challenge.requesting_team
                points = challenge.current_value
            else:
                winner = player.team.opponent
                points = session.hand_value
            await self._award_hand(session, winner, points, ran_by=user_id)
            await self._record(
                session,
                user_id,
                TrucoActionType.RUN,
                {"winner": winner.value, "points": points},
            )
            return await self._repository.update_game(session)

    async def get_game(self, game_id: int) -> TrucoSession | None:
        return await self._repository.get_game(game_id)

    async def reset_user_state(self, guild_id: int, user_id: int) -> None:
        async with self._lock:
            games = await self._repository.list_active_games_for_user(
                guild_id,
                user_id,
            )
            for session in games:
                if session.status is TrucoGameStatus.PLAYING:
                    await self._refund_all(session)
                session.status = TrucoGameStatus.CANCELLED
                session.finished_at = utc_now()
                await self._record(session, user_id, TrucoActionType.CANCEL)
                await self._repository.update_game(session)

    async def _start_game(self, session: TrucoSession) -> None:
        await self._debit_all(session)
        self._start_new_hand(session)

    def _start_new_hand(self, session: TrucoSession) -> None:
        deck = self._build_deck()
        self._rng.shuffle(deck)
        ordered_players = sorted(session.players, key=lambda item: item.seat_position)
        session.hands = {player.user_id: [] for player in ordered_players}
        for _ in range(3):
            for player in ordered_players:
                session.hands[player.user_id].append(deck.pop(0))
        session.vira = deck.pop(0)
        session.manilha_rank = self._next_rank(session.vira.rank)
        session.round_number = 1
        session.round_winners = []
        session.played_cards = []
        session.pending_challenge = None
        session.current_turn_user_id = self._player_by_position(
            session,
            session.hand_starter_position,
        ).user_id
        session.round_starter_position = session.hand_starter_position
        session.is_escurona = (
            session.score_blue == self.WINNING_SCORE - 1
            and session.score_red == self.WINNING_SCORE - 1
        )
        session.hand_value = 3 if self._is_hand_of_eleven(session) else 1
        session.status = TrucoGameStatus.PLAYING

    async def _finish_round(self, session: TrucoSession) -> None:
        round_winner, winner_position = self._resolve_round_result(session)
        session.round_winners.append(round_winner)
        winner_user_id = (
            self._player_by_position(session, winner_position).user_id
            if winner_position is not None
            else None
        )
        session.last_round_reveal = TrucoRoundReveal(
            hand_number=session.hand_number,
            round_number=session.round_number,
            hand_value=session.hand_value,
            cards=list(self._round_cards(session)),
            winner=round_winner,
            winner_user_id=winner_user_id,
            score_blue_before=session.score_blue,
            score_red_before=session.score_red,
            round_wins_blue=session.round_winners.count(TrucoTeam.BLUE),
            round_wins_red=session.round_winners.count(TrucoTeam.RED),
            vira=session.vira,
            manilha_rank=session.manilha_rank,
        )
        session.round_reveal_pending = session.game_mode is TrucoGameMode.PVE
        hand_winner = self._resolve_hand_winner(session)
        if hand_winner is not None:
            await self._award_hand(
                session,
                hand_winner,
                session.hand_value,
                ran_by=None,
            )
            return

        session.round_number += 1
        if winner_position is not None:
            starter = self._player_by_position(session, winner_position)
            session.current_turn_user_id = starter.user_id
            session.round_starter_position = starter.seat_position
        else:
            session.current_turn_user_id = self._player_by_position(
                session,
                session.round_starter_position,
            ).user_id

    async def _award_hand(
        self,
        session: TrucoSession,
        winner: TrucoTeam,
        points: int,
        *,
        ran_by: int | None,
    ) -> None:
        next_score = min(self.WINNING_SCORE, session.score(winner) + points)
        session.set_score(winner, next_score)
        await self._record(
            session,
            ran_by,
            TrucoActionType.FINISH_HAND,
            {
                "winner": winner.value,
                "points": points,
                "score_blue": session.score_blue,
                "score_red": session.score_red,
            },
        )
        if session.score(winner) >= self.WINNING_SCORE:
            await self._finish_game(session, winner)
            return
        session.hand_number += 1
        session.hand_starter_position = (session.hand_starter_position + 1) % len(
            session.players
        )
        self._start_new_hand(session)

    async def _finish_game(self, session: TrucoSession, winner: TrucoTeam) -> None:
        session.status = TrucoGameStatus.FINISHED
        session.winning_team = winner
        session.finished_at = utc_now()
        losing_team = winner.opponent
        if session.score(losing_team) == 0:
            losers = " e ".join(
                self._player_reference(player)
                for player in session.team_players(losing_team)
            )
            session.zero_loss_announcement = (
                f"A dupla perdedora {losers} vai passar debaixo da mesa"
            )
        await self._pay_winners(session, winner)
        await self._record(
            session,
            None,
            TrucoActionType.FINISH_GAME,
            {"winner": winner.value},
        )

    async def _debit_all(self, session: TrucoSession) -> None:
        settings = await self._economy_repository.get_guild_settings(session.guild_id)
        snapshots: dict[int, dict[str, object]] = {}
        for player in session.players:
            if player.is_bot:
                continue
            decision = await self._economic_policy.select(
                settings,
                guild_id=session.guild_id,
                user_id=player.user_id,
                game="truco",
            )
            if (
                decision.limiters_apply
                and decision.daily_profit >= decision.daily_limit
            ):
                raise TrucoValidationError(
                    f"<@{player.user_id}> atingiu o teto diario de lucro dos jogos."
                )
            snapshots[player.user_id] = self._economic_policy.snapshot(decision)
        session.economic_policy_snapshots = snapshots
        debited: list[tuple[int, int]] = []
        for player in session.players:
            if player.is_bot:
                continue
            try:
                debit = await self._economy_repository.mutate_balance(
                    guild_id=session.guild_id,
                    user_id=player.user_id,
                    amount=-session.stake,
                    transaction_type=EconomyTransactionType.CASINO_BET,
                    actor_id=None,
                    reason="truco_stake",
                    metadata={
                        "game": "truco",
                        "game_id": session.id,
                        "team": player.team.value,
                        "stake": session.stake,
                    },
                )
                debited.append((player.user_id, debit.transaction.id))
            except Exception as exc:
                for user_id, transaction_id in debited:
                    await self._refund_player(
                        session,
                        user_id,
                        "truco_failed_start",
                        idempotency_key=(f"truco:debit:{transaction_id}:refund"),
                    )
                session.economic_policy_snapshots = {}
                if isinstance(exc, ValueError):
                    raise TrucoValidationError(
                        f"<@{player.user_id}> não possui saldo suficiente."
                    ) from exc
                raise

    async def _pay_winners(self, session: TrucoSession, winner: TrucoTeam) -> None:
        winners = session.team_players(winner)
        losers = session.team_players(winner.opponent)
        human_winners = [player for player in winners if not player.is_bot]
        payout_per_winner = (
            session.stake * 2
            if session.game_mode is TrucoGameMode.PVE
            else (session.pot * 125 // 100) // max(1, len(human_winners))
        )
        for player in winners:
            if player.is_bot:
                continue
            settings = await self._economy_repository.get_guild_settings(
                session.guild_id
            )
            decision = await self._economic_policy.decision_for_settlement(
                session.economic_policy_snapshots.get(player.user_id),
                settings,
                guild_id=session.guild_id,
                user_id=player.user_id,
                game="truco",
                stake=session.stake,
            )
            await self._economic_policy.settle_payout(
                decision,
                guild_id=session.guild_id,
                user_id=player.user_id,
                stake=session.stake,
                payout=payout_per_winner,
                transaction_type=EconomyTransactionType.CASINO_PAYOUT,
                reason="truco_payout",
                metadata={
                    "game": "truco",
                    "game_id": session.id,
                    "team": winner.value,
                    "payout": payout_per_winner,
                    "uncapped_payout": payout_per_winner,
                    "outcome": "WON",
                },
                idempotency_key=f"truco:{session.id}:{player.user_id}",
            )
            await self._economy_repository.apply_credit_protection(
                guild_id=session.guild_id,
                user_id=player.user_id,
                game_key="truco",
                stake=session.stake,
                is_loss=False,
                metadata={"source": "truco", "game_id": session.id},
                idempotency_key=f"truco:{session.id}:{player.user_id}:credit",
            )
            await self._unlock_progress(session.guild_id, player.user_id, won=True)

        for player in losers:
            if player.is_bot:
                continue
            await self._economy_repository.apply_credit_protection(
                guild_id=session.guild_id,
                user_id=player.user_id,
                game_key="truco",
                stake=session.stake,
                is_loss=True,
                metadata={"source": "truco", "game_id": session.id},
                idempotency_key=f"truco:{session.id}:{player.user_id}:credit",
            )
            await self._unlock_progress(session.guild_id, player.user_id, won=False)

    async def _refund_all(self, session: TrucoSession) -> None:
        for player in session.players:
            if player.is_bot:
                continue
            await self._refund_player(session, player.user_id, "truco_cancel_refund")

    async def _refund_player(
        self,
        session: TrucoSession,
        user_id: int,
        reason: str,
        *,
        idempotency_key: str | None = None,
    ) -> None:
        await self._economy_repository.mutate_balance(
            guild_id=session.guild_id,
            user_id=user_id,
            amount=session.stake,
            transaction_type=EconomyTransactionType.REFUND,
            actor_id=None,
            reason=reason,
            metadata={"game": "truco", "game_id": session.id, "stake": session.stake},
            idempotency_key=(idempotency_key or f"truco:{session.id}:{user_id}:refund"),
        )

    async def _unlock_progress(self, guild_id: int, user_id: int, *, won: bool) -> None:
        if self._progress_service is None:
            return
        await self._progress_service.unlock(guild_id, user_id, "first_bet")
        achievement = "first_win" if won else "first_loss"
        await self._progress_service.unlock(guild_id, user_id, achievement)
        await self._progress_service.evaluate_user_milestones(guild_id, user_id)

    def _resolve_round_result(
        self,
        session: TrucoSession,
    ) -> tuple[TrucoTeam | None, int | None]:
        cards = self._round_cards(session)
        best = cards[0]
        tied = False
        for played in cards[1:]:
            comparison = self._compare_played_cards(session, played, best)
            if comparison > 0:
                best = played
                tied = False
            elif comparison == 0:
                tied = True
        if tied:
            return None, None
        best_player = self._require_player(session, best.user_id)
        return best_player.team, best_player.seat_position

    def _resolve_hand_winner(self, session: TrucoSession) -> TrucoTeam | None:
        blue_wins = session.round_winners.count(TrucoTeam.BLUE)
        red_wins = session.round_winners.count(TrucoTeam.RED)
        if blue_wins >= 2:
            return TrucoTeam.BLUE
        if red_wins >= 2:
            return TrucoTeam.RED
        if len(session.round_winners) == 2:
            first, second = session.round_winners
            if first is None and second is not None:
                return second
            if first is not None and second is None:
                return first
        if len(session.round_winners) >= 3:
            if blue_wins > red_wins:
                return TrucoTeam.BLUE
            if red_wins > blue_wins:
                return TrucoTeam.RED
            return self._player_by_position(
                session,
                session.hand_starter_position,
            ).team
        return None

    def _compare_played_cards(
        self,
        session: TrucoSession,
        left: TrucoPlayedCard,
        right: TrucoPlayedCard,
    ) -> int:
        left_power = self._card_power(session, left.card, left.is_closed)
        right_power = self._card_power(session, right.card, right.is_closed)
        return (left_power > right_power) - (left_power < right_power)

    def _card_power(
        self,
        session: TrucoSession,
        card: TrucoCard,
        is_closed: bool,
    ) -> tuple[int, int]:
        if is_closed:
            return (-1, -1)
        if card.rank is session.manilha_rank:
            return (100, TRUCO_SUIT_POWER[card.suit])
        return (TRUCO_RANK_ORDER.index(card.rank), 0)

    def _round_cards(self, session: TrucoSession) -> list[TrucoPlayedCard]:
        return [
            played
            for played in session.played_cards
            if played.round_number == session.round_number
        ]

    def _next_turn_user_id(self, session: TrucoSession, current_position: int) -> int:
        next_position = (current_position + 1) % len(session.players)
        return self._player_by_position(session, next_position).user_id

    def _player_by_position(
        self,
        session: TrucoSession,
        position: int,
    ) -> TrucoPlayer:
        normalized = position % len(session.players)
        for player in session.players:
            if player.seat_position == normalized:
                return player
        raise TrucoValidationError("Ordem da mesa inválida.")

    def _require_player(self, session: TrucoSession, user_id: int) -> TrucoPlayer:
        player = session.player(user_id)
        if player is None:
            raise TrucoValidationError("Você não participa desta partida.")
        return player

    async def _require_game(self, game_id: int) -> TrucoSession:
        session = await self._repository.get_game(game_id)
        if session is None:
            raise TrucoValidationError("Partida de Truco não encontrada.")
        return session

    @staticmethod
    def _require_status(session: TrucoSession, status: TrucoGameStatus) -> None:
        if session.status is not status:
            raise TrucoValidationError("Esta partida não está nessa etapa.")

    @staticmethod
    def _require_playing(session: TrucoSession) -> None:
        if session.status is not TrucoGameStatus.PLAYING:
            raise TrucoValidationError("Esta partida não está em andamento.")

    @staticmethod
    def _require_reveal_complete(session: TrucoSession) -> None:
        if session.round_reveal_pending:
            raise TrucoValidationError(
                "Aguarde a apresentação do resultado da rodada anterior."
            )

    def _require_challenge_response(
        self,
        session: TrucoSession,
        user_id: int,
    ) -> TrucoChallenge:
        self._require_playing(session)
        challenge = session.pending_challenge
        if challenge is None:
            raise TrucoValidationError("Não existe pedido de Truco pendente.")
        player = self._require_player(session, user_id)
        if player.team is not challenge.target_team:
            raise TrucoValidationError("Apenas a dupla desafiada pode responder.")
        return challenge

    @classmethod
    def _next_truco_value(cls, current: int) -> int:
        try:
            index = TRUCO_VALUES.index(current)
        except ValueError as exc:
            raise TrucoValidationError("Valor da mão inválido.") from exc
        if index + 1 >= len(TRUCO_VALUES):
            raise TrucoValidationError("A mão já está no valor máximo.")
        return TRUCO_VALUES[index + 1]

    @staticmethod
    def _next_rank(rank: TrucoRank) -> TrucoRank:
        index = TRUCO_RANK_ORDER.index(rank)
        return TRUCO_RANK_ORDER[(index + 1) % len(TRUCO_RANK_ORDER)]

    @staticmethod
    def _is_hand_of_eleven(session: TrucoSession) -> bool:
        return session.score_blue == 11 or session.score_red == 11

    async def _validate_daily_profit_limit(self, guild_id: int, user_id: int) -> None:
        settings = await self._economy_repository.get_guild_settings(guild_id)
        decision = await self._economic_policy.select(
            settings,
            guild_id=guild_id,
            user_id=user_id,
            game="truco",
        )
        if decision.limiters_apply and decision.daily_profit >= decision.daily_limit:
            raise TrucoValidationError("Você atingiu o teto diário de lucro dos jogos.")

    @classmethod
    def _validate_stake(cls, stake: int, min_stake: int, max_stake: int) -> None:
        if stake < min_stake:
            raise TrucoValidationError(
                f"A aposta mínima para Truco é de {min_stake} ponto(s)."
            )
        if stake > max_stake:
            raise TrucoValidationError(
                f"A aposta máxima para Truco é de {max_stake} ponto(s)."
            )

    @staticmethod
    def _build_deck() -> list[TrucoCard]:
        return [
            TrucoCard(rank=rank, suit=suit)
            for suit in TrucoSuit
            for rank in TRUCO_RANK_ORDER
        ]

    async def _record(
        self,
        session: TrucoSession,
        user_id: int | None,
        action_type: TrucoActionType,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if session.id is None:
            return
        await self._repository.record_action(
            game_id=session.id,
            user_id=user_id,
            action_type=action_type,
            metadata=metadata or {},
        )

    async def play_machine_turns(self, game_id: int) -> TrucoSession:
        while True:
            session = await self._require_game(game_id)
            if session.status is not TrucoGameStatus.PLAYING:
                return session
            if session.round_reveal_pending:
                return session
            challenge = session.pending_challenge
            if challenge is not None:
                target_bots = [
                    player
                    for player in session.team_players(challenge.target_team)
                    if player.is_bot
                ]
                if target_bots:
                    bot = target_bots[0]
                    hand = session.hands.get(bot.user_id, [])
                    strong = any(
                        card.rank is session.manilha_rank
                        or card.rank in {TrucoRank.THREE, TrucoRank.TWO, TrucoRank.ACE}
                        for card in hand
                    )
                    if strong:
                        await self.accept_truco(game_id, bot.user_id)
                    else:
                        await self.run(game_id, bot.user_id)
                    continue
                return session
            current = session.player(session.current_turn_user_id or 0)
            if current is None or not current.is_bot:
                return session
            hand = session.hands.get(current.user_id, [])
            if not hand:
                return session
            card_index = self._machine_card_index(session, current, hand)
            await self.play_card(
                game_id=game_id,
                user_id=current.user_id,
                card_index=card_index,
                closed=False,
            )

    async def consume_round_reveal(
        self,
        game_id: int,
        reveal_key: str,
    ) -> TrucoSession:
        """Libera a próxima ação após a apresentação visual da rodada."""

        async with self._lock:
            session = await self._require_game(game_id)
            reveal = session.last_round_reveal
            if (
                session.round_reveal_pending
                and reveal is not None
                and reveal.key == reveal_key
            ):
                session.round_reveal_pending = False
                return await self._repository.update_game(session)
            return session

    def _machine_card_index(
        self,
        session: TrucoSession,
        player: TrucoPlayer,
        hand: list[TrucoCard],
    ) -> int:
        ordered = sorted(
            enumerate(hand),
            key=lambda item: self._card_power(session, item[1], False),
        )
        round_cards = self._round_cards(session)
        if not round_cards:
            return ordered[0][0]
        best_table = max(
            self._card_power(session, played.card, played.is_closed)
            for played in round_cards
        )
        for index, card in ordered:
            if self._card_power(session, card, False) > best_table:
                return index
        return ordered[0][0]

    @staticmethod
    def _player_reference(player: TrucoPlayer) -> str:
        return "Máquina" if player.is_bot else f"<@{player.user_id}>"
