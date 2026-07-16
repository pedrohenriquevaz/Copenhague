from __future__ import annotations

import asyncio
import random

from app.models.economy import EconomyTransactionType
from app.models.giveaway import utc_now
from app.models.uno import (
    UnoActionType,
    UnoCard,
    UnoColor,
    UnoGameMode,
    UnoGameStatus,
    UnoPlayer,
    UnoSession,
    UnoValue,
)
from app.repositories.economy_protocol import EconomyRepositoryProtocol
from app.repositories.uno_repository import UnoRepositoryProtocol
from app.services.economic_tier_service import EconomicTierService
from app.services.economy_limits import EconomicDifficultyPolicyService


class UnoServiceError(Exception):
    """Erro base do UNO."""


class UnoValidationError(UnoServiceError):
    """Ação inválida em uma partida de UNO."""


class UnoService:
    MIN_PLAYERS = 2
    MAX_PLAYERS = 10
    INITIAL_HAND_SIZE = 7
    MACHINE_USER_ID = -1

    def __init__(
        self,
        repository: UnoRepositoryProtocol,
        economy_repository: EconomyRepositoryProtocol,
        *,
        rng: random.Random | random.SystemRandom | None = None,
        economic_policy: EconomicDifficultyPolicyService | None = None,
    ) -> None:
        self._repository = repository
        self._economy_repository = economy_repository
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
        title: str,
        stake: int,
    ) -> UnoSession:
        clean_title = " ".join(title.split())
        if not clean_title:
            raise UnoValidationError("Informe um nome para a partida.")
        if len(clean_title) > 60:
            raise UnoValidationError("O nome da partida pode ter até 60 caracteres.")
        async with self._lock:
            if await self._repository.get_active_game_for_channel(
                guild_id,
                channel_id,
            ):
                raise UnoValidationError(
                    "Este canal já possui uma partida de UNO ativa."
                )
            await self._validate_stake_and_balance(guild_id, created_by, stake)
            if await self._repository.list_active_games_for_user(
                guild_id,
                created_by,
            ):
                raise UnoValidationError(
                    "Você já participa de uma partida de UNO ativa."
                )

            session = UnoSession(
                id=None,
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=None,
                title=clean_title,
                created_by=created_by,
                status=UnoGameStatus.LOBBY,
                players=[UnoPlayer(created_by)],
                stake=stake,
                game_mode=UnoGameMode.PVP,
            )
            created = await self._repository.create_game(session)
            await self._record(created, created_by, UnoActionType.CREATE)
            return created

    async def create_pve_game(
        self,
        *,
        guild_id: int,
        channel_id: int,
        created_by: int,
        title: str,
        stake: int,
    ) -> UnoSession:
        clean_title = " ".join(title.split())
        if not clean_title or len(clean_title) > 60:
            raise UnoValidationError("O nome da partida deve ter de 1 a 60 caracteres.")
        async with self._lock:
            if await self._repository.get_active_game_for_channel(guild_id, channel_id):
                raise UnoValidationError(
                    "Este canal já possui uma partida de UNO ativa."
                )
            if await self._repository.list_active_games_for_user(guild_id, created_by):
                raise UnoValidationError(
                    "Você já participa de uma partida de UNO ativa."
                )
            await self._validate_stake_and_balance(guild_id, created_by, stake)
            session = UnoSession(
                id=None,
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=None,
                title=clean_title,
                created_by=created_by,
                status=UnoGameStatus.LOBBY,
                players=[
                    UnoPlayer(created_by),
                    UnoPlayer(self.MACHINE_USER_ID, is_bot=True),
                ],
                stake=stake,
                game_mode=UnoGameMode.PVE,
            )
            session = await self._repository.create_game(session)
            await self._record(session, created_by, UnoActionType.CREATE)
            await self._debit_stakes(session)
            self._deal_cards(session)
            await self._record(session, created_by, UnoActionType.START)
            return await self._repository.update_game(session)

    async def attach_message(self, game_id: int, message_id: int) -> UnoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            session.message_id = message_id
            return await self._repository.update_game(session)

    async def join_game(self, game_id: int, user_id: int) -> UnoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_status(session, UnoGameStatus.LOBBY)
            if session.player(user_id) is not None:
                raise UnoValidationError("Você já está nesta partida.")
            if len(session.players) >= self.MAX_PLAYERS:
                raise UnoValidationError("A mesa atingiu o limite de 10 jogadores.")
            other_games = await self._repository.list_active_games_for_user(
                session.guild_id,
                user_id,
            )
            if other_games:
                raise UnoValidationError("Você já participa de outra partida de UNO.")
            await self._validate_stake_and_balance(
                session.guild_id,
                user_id,
                session.stake,
            )
            session.players.append(UnoPlayer(user_id))
            session.last_action = f"<@{user_id}> entrou na partida."
            await self._record(session, user_id, UnoActionType.JOIN)
            return await self._repository.update_game(session)

    async def leave_game(self, game_id: int, user_id: int) -> UnoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_status(session, UnoGameStatus.LOBBY)
            if user_id == session.created_by:
                raise UnoValidationError(
                    "O criador deve usar Encerrar Partida para fechar a mesa."
                )
            player = self._require_player(session, user_id)
            session.players.remove(player)
            session.last_action = f"<@{user_id}> saiu da partida."
            await self._record(session, user_id, UnoActionType.LEAVE)
            return await self._repository.update_game(session)

    async def start_game(self, game_id: int, user_id: int) -> UnoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_status(session, UnoGameStatus.LOBBY)
            if user_id != session.created_by:
                raise UnoValidationError("Apenas o criador pode iniciar a partida.")
            if len(session.players) < self.MIN_PLAYERS:
                raise UnoValidationError("São necessários pelo menos 2 jogadores.")

            await self._debit_stakes(session)
            self._deal_cards(session)
            await self._record(session, user_id, UnoActionType.START)
            return await self._repository.update_game(session)

    async def play_card(
        self,
        *,
        game_id: int,
        user_id: int,
        card_id: int,
        chosen_color: UnoColor | None = None,
    ) -> UnoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_turn(session, user_id)
            player = self._require_player(session, user_id)
            card = next((item for item in player.hand if item.id == card_id), None)
            if card is None:
                raise UnoValidationError("Essa carta não está mais na sua mão.")
            if session.drawn_card_id is not None and card.id != session.drawn_card_id:
                raise UnoValidationError(
                    "Depois de comprar, você só pode jogar a carta comprada ou passar."
                )
            if not self.is_playable(session, card):
                raise UnoValidationError("Essa carta não pode ser jogada agora.")
            if card.value.is_wild and chosen_color is None:
                raise UnoValidationError(
                    "Escolha a nova cor antes de jogar esta carta."
                )

            player.hand.remove(card)
            session.discard_pile.append(card)
            session.current_color = chosen_color if card.value.is_wild else card.color
            session.drawn_card_id = None
            reference = self._player_reference(session, user_id)
            session.last_action = f"{reference} jogou {card.short_label}."
            if chosen_color is not None:
                session.last_action += f" A cor agora é {chosen_color.label}."
            await self._record(
                session,
                user_id,
                UnoActionType.PLAY_CARD,
                {
                    "card_id": card.id,
                    "card": card.label,
                    "chosen_color": chosen_color.value if chosen_color else None,
                },
            )

            if not player.hand:
                session.status = UnoGameStatus.FINISHED
                session.winner_user_id = user_id
                session.finished_at = utc_now()
                session.last_action = f"{reference} venceu a partida!"
                await self._settle_game(session, player)
                await self._record(session, user_id, UnoActionType.FINISH)
                return await self._repository.update_game(session)

            self._apply_card_effect(session, card)
            return await self._repository.update_game(session)

    async def draw_card(self, game_id: int, user_id: int) -> UnoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_turn(session, user_id)
            if session.drawn_card_id is not None:
                raise UnoValidationError("Você já comprou uma carta neste turno.")
            player = self._require_player(session, user_id)
            card = self._draw_cards(session, player, 1)[0]
            await self._record(
                session,
                user_id,
                UnoActionType.DRAW_CARD,
                {"card_id": card.id},
            )
            if self.is_playable(session, card):
                session.drawn_card_id = card.id
                session.last_action = (
                    f"{self._player_reference(session, user_id)} comprou uma carta "
                    "e pode jogá-la ou passar."
                )
            else:
                session.last_action = (
                    f"{self._player_reference(session, user_id)} comprou uma carta "
                    "e passou."
                )
                self._advance(session)
            return await self._repository.update_game(session)

    async def pass_turn(self, game_id: int, user_id: int) -> UnoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            self._require_turn(session, user_id)
            if session.drawn_card_id is None:
                raise UnoValidationError(
                    "Você precisa comprar uma carta antes de passar."
                )
            session.drawn_card_id = None
            session.last_action = (
                f"{self._player_reference(session, user_id)} decidiu passar."
            )
            await self._record(session, user_id, UnoActionType.PASS)
            self._advance(session)
            return await self._repository.update_game(session)

    async def cancel_game(
        self,
        game_id: int,
        user_id: int,
        *,
        is_admin: bool = False,
        reason: str = "Partida encerrada manualmente.",
    ) -> UnoSession:
        async with self._lock:
            session = await self._require_game(game_id)
            if session.status not in {UnoGameStatus.LOBBY, UnoGameStatus.PLAYING}:
                raise UnoValidationError("Esta partida já foi encerrada.")
            if user_id != session.created_by and not is_admin:
                raise UnoValidationError(
                    "Apenas o criador ou um administrador pode encerrar a partida."
                )
            await self._refund_stakes(session, reason="uno_cancel_refund")
            session.status = UnoGameStatus.CANCELLED
            session.finished_at = utc_now()
            session.last_action = reason.strip()[:500] or "Partida cancelada."
            await self._record(
                session,
                user_id,
                UnoActionType.CANCEL,
                {"reason": session.last_action, "is_admin": is_admin},
            )
            return await self._repository.update_game(session)

    async def cancel_deleted_message(self, message_id: int) -> UnoSession | None:
        async with self._lock:
            session = await self._repository.get_game_by_message_id(message_id)
            if session is None or session.status not in {
                UnoGameStatus.LOBBY,
                UnoGameStatus.PLAYING,
            }:
                return None
            await self._refund_stakes(session, reason="uno_deleted_message_refund")
            session.status = UnoGameStatus.CANCELLED
            session.finished_at = utc_now()
            session.last_action = "Partida cancelada porque a mesa foi apagada."
            await self._record(session, None, UnoActionType.CANCEL, {"deleted": True})
            return await self._repository.update_game(session)

    async def get_game(self, game_id: int) -> UnoSession | None:
        return await self._repository.get_game(game_id)

    async def reset_user_state(self, guild_id: int, user_id: int) -> None:
        async with self._lock:
            games = await self._repository.list_active_games_for_user(
                guild_id,
                user_id,
            )
            for session in games:
                await self._refund_stakes(session, reason="uno_profile_reset_refund")
                session.status = UnoGameStatus.CANCELLED
                session.finished_at = utc_now()
                session.last_action = "Partida cancelada por reset de perfil."
                await self._record(session, user_id, UnoActionType.CANCEL)
                await self._repository.update_game(session)

    @staticmethod
    def build_deck() -> list[UnoCard]:
        cards: list[UnoCard] = []
        card_id = 1
        number_values = (
            UnoValue.ONE,
            UnoValue.TWO,
            UnoValue.THREE,
            UnoValue.FOUR,
            UnoValue.FIVE,
            UnoValue.SIX,
            UnoValue.SEVEN,
            UnoValue.EIGHT,
            UnoValue.NINE,
        )
        for color in UnoColor:
            cards.append(UnoCard(card_id, color, UnoValue.ZERO))
            card_id += 1
            for value in number_values:
                for _ in range(2):
                    cards.append(UnoCard(card_id, color, value))
                    card_id += 1
            for value in (UnoValue.SKIP, UnoValue.REVERSE, UnoValue.DRAW_TWO):
                for _ in range(2):
                    cards.append(UnoCard(card_id, color, value))
                    card_id += 1
        for _ in range(4):
            cards.append(UnoCard(card_id, None, UnoValue.WILD))
            card_id += 1
            cards.append(UnoCard(card_id, None, UnoValue.WILD_DRAW_FOUR))
            card_id += 1
        return cards

    @staticmethod
    def is_playable(session: UnoSession, card: UnoCard) -> bool:
        top = session.top_card
        if top is None or card.value.is_wild:
            return True
        return card.color is session.current_color or card.value is top.value

    def _apply_card_effect(self, session: UnoSession, card: UnoCard) -> None:
        if card.value is UnoValue.REVERSE:
            session.direction *= -1
            self._advance(session, steps=2 if len(session.players) == 2 else 1)
            return
        if card.value is UnoValue.SKIP:
            self._advance(session, steps=2)
            return
        if card.value in {UnoValue.DRAW_TWO, UnoValue.WILD_DRAW_FOUR}:
            amount = 2 if card.value is UnoValue.DRAW_TWO else 4
            target_index = self._next_index(session)
            target = session.players[target_index]
            self._draw_cards(session, target, amount)
            target_name = self._player_reference(session, target.user_id)
            session.last_action += f" {target_name} comprou {amount} e perdeu a vez."
            session.current_player_index = self._next_index(
                session,
                from_index=target_index,
            )
            return
        self._advance(session)

    def _draw_cards(
        self,
        session: UnoSession,
        player: UnoPlayer,
        amount: int,
    ) -> list[UnoCard]:
        drawn: list[UnoCard] = []
        for _ in range(amount):
            self._recycle_deck(session)
            if not session.draw_pile:
                raise UnoValidationError("Não há cartas disponíveis no monte.")
            card = session.draw_pile.pop()
            player.hand.append(card)
            drawn.append(card)
        return drawn

    def _recycle_deck(self, session: UnoSession) -> None:
        if session.draw_pile or len(session.discard_pile) <= 1:
            return
        top = session.discard_pile[-1]
        recycled = session.discard_pile[:-1]
        self._rng.shuffle(recycled)
        session.draw_pile = recycled
        session.discard_pile = [top]

    def _advance(self, session: UnoSession, *, steps: int = 1) -> None:
        for _ in range(steps):
            session.current_player_index = self._next_index(session)
        session.drawn_card_id = None

    async def play_machine_turns(self, game_id: int) -> UnoSession:
        while True:
            session = await self._require_game(game_id)
            current = session.current_player
            if (
                session.status is not UnoGameStatus.PLAYING
                or current is None
                or not current.is_bot
            ):
                return session
            playable = [
                card for card in current.hand if self.is_playable(session, card)
            ]
            if playable:
                card = max(playable, key=self._machine_card_priority)
                color = (
                    self._machine_color(current.hand) if card.value.is_wild else None
                )
                await self.play_card(
                    game_id=game_id,
                    user_id=current.user_id,
                    card_id=card.id,
                    chosen_color=color,
                )
                continue
            drawn = await self.draw_card(game_id, current.user_id)
            if drawn.current_player and drawn.current_player.is_bot:
                bot = drawn.current_player
                card = next(
                    (item for item in bot.hand if item.id == drawn.drawn_card_id),
                    None,
                )
                if card is not None:
                    color = (
                        self._machine_color(bot.hand) if card.value.is_wild else None
                    )
                    await self.play_card(
                        game_id=game_id,
                        user_id=bot.user_id,
                        card_id=card.id,
                        chosen_color=color,
                    )

    def _deal_cards(self, session: UnoSession) -> None:
        deck = self.build_deck()
        self._rng.shuffle(deck)
        for player in session.players:
            player.hand = [deck.pop() for _ in range(self.INITIAL_HAND_SIZE)]
        initial_index = next(
            (
                index
                for index, card in enumerate(deck)
                if card.color is not None
                and card.value
                not in {UnoValue.SKIP, UnoValue.REVERSE, UnoValue.DRAW_TWO}
            ),
            None,
        )
        if initial_index is None:
            raise UnoServiceError("O baralho não possui carta inicial válida.")
        initial_card = deck.pop(initial_index)
        session.draw_pile = deck
        session.discard_pile = [initial_card]
        session.current_player_index = 0
        session.direction = 1
        session.current_color = initial_card.color
        session.drawn_card_id = None
        session.status = UnoGameStatus.PLAYING
        first_player = self._player_reference(session, session.players[0].user_id)
        session.last_action = f"Partida iniciada. {first_player} joga primeiro."

    async def _validate_stake_and_balance(
        self,
        guild_id: int,
        user_id: int,
        stake: int,
    ) -> None:
        settings = await self._economy_repository.get_guild_settings(guild_id)
        if stake < 1 or stake > settings.casino_max_bet:
            raise UnoValidationError(
                f"A aposta deve estar entre 1 e {settings.casino_max_bet} ponto(s)."
            )
        wallet = await self._economy_repository.get_wallet(guild_id, user_id)
        if wallet.balance < stake:
            raise UnoValidationError("Você não possui saldo suficiente para a aposta.")

    async def _debit_stakes(self, session: UnoSession) -> None:
        settings = await self._economy_repository.get_guild_settings(session.guild_id)
        snapshots: dict[int, dict[str, object]] = {}
        for player in session.human_players:
            decision = await self._economic_policy.select(
                settings,
                guild_id=session.guild_id,
                user_id=player.user_id,
                game="uno",
            )
            snapshots[player.user_id] = self._economic_policy.snapshot(decision)
        session.economic_policy_snapshots = snapshots
        debited: list[tuple[int, int]] = []
        try:
            for player in session.human_players:
                debit = await self._economy_repository.mutate_balance(
                    guild_id=session.guild_id,
                    user_id=player.user_id,
                    amount=-session.stake,
                    transaction_type=EconomyTransactionType.CASINO_BET,
                    actor_id=None,
                    reason="uno_stake",
                    metadata={"game": "uno", "game_id": session.id},
                )
                debited.append((player.user_id, debit.transaction.id))
        except Exception as exc:
            for user_id, transaction_id in debited:
                await self._refund_player(
                    session,
                    user_id,
                    "uno_failed_start",
                    idempotency_key=f"uno:debit:{transaction_id}:refund",
                )
            session.economic_policy_snapshots = {}
            if isinstance(exc, ValueError):
                raise UnoValidationError(
                    "Um participante não possui saldo suficiente."
                ) from exc
            raise
        session.stakes_debited = True

    async def _settle_game(self, session: UnoSession, winner: UnoPlayer) -> None:
        if not session.stakes_debited:
            return
        for player in session.human_players:
            won = player.user_id == winner.user_id
            if won:
                payout = session.expected_winner_payout
                settings = await self._economy_repository.get_guild_settings(
                    session.guild_id
                )
                decision = await self._economic_policy.decision_for_settlement(
                    session.economic_policy_snapshots.get(player.user_id),
                    settings,
                    guild_id=session.guild_id,
                    user_id=player.user_id,
                    game="uno",
                    stake=session.stake,
                )
                await self._economic_policy.settle_payout(
                    decision,
                    guild_id=session.guild_id,
                    user_id=player.user_id,
                    stake=session.stake,
                    payout=payout,
                    transaction_type=EconomyTransactionType.CASINO_PAYOUT,
                    reason="uno_payout",
                    metadata={
                        "game": "uno",
                        "game_id": session.id,
                        "mode": session.game_mode.value,
                    },
                    idempotency_key=f"uno:{session.id}:{player.user_id}",
                )
            await self._economy_repository.apply_credit_protection(
                guild_id=session.guild_id,
                user_id=player.user_id,
                game_key="uno",
                stake=session.stake,
                is_loss=not won,
                metadata={"source": "uno", "game_id": session.id},
                idempotency_key=f"uno:{session.id}:{player.user_id}:credit",
            )
        session.stakes_debited = False

    async def _refund_stakes(self, session: UnoSession, *, reason: str) -> None:
        if not session.stakes_debited:
            return
        for player in session.human_players:
            await self._refund_player(session, player.user_id, reason)
        session.stakes_debited = False

    async def _refund_player(
        self,
        session: UnoSession,
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
            metadata={"game": "uno", "game_id": session.id},
            idempotency_key=(
                idempotency_key or f"uno:{session.id}:{user_id}:refund"
            ),
        )

    @staticmethod
    def _machine_card_priority(card: UnoCard) -> tuple[int, int]:
        priority = {
            UnoValue.WILD_DRAW_FOUR: 5,
            UnoValue.DRAW_TWO: 4,
            UnoValue.SKIP: 3,
            UnoValue.REVERSE: 2,
            UnoValue.WILD: 1,
        }.get(card.value, 0)
        return priority, card.id

    @staticmethod
    def _machine_color(hand: list[UnoCard]) -> UnoColor:
        counts = {
            color: sum(card.color is color for card in hand) for color in UnoColor
        }
        return max(UnoColor, key=lambda color: counts[color])

    @staticmethod
    def _player_reference(session: UnoSession, user_id: int) -> str:
        player = session.player(user_id)
        return "Máquina" if player and player.is_bot else f"<@{user_id}>"

    @staticmethod
    def _next_index(session: UnoSession, *, from_index: int | None = None) -> int:
        start = session.current_player_index if from_index is None else from_index
        return (start + session.direction) % len(session.players)

    async def _require_game(self, game_id: int) -> UnoSession:
        session = await self._repository.get_game(game_id)
        if session is None:
            raise UnoValidationError("Partida de UNO não encontrada.")
        return session

    @staticmethod
    def _require_status(session: UnoSession, status: UnoGameStatus) -> None:
        if session.status is not status:
            raise UnoValidationError("Esta partida não está nessa etapa.")

    @staticmethod
    def _require_player(session: UnoSession, user_id: int) -> UnoPlayer:
        player = session.player(user_id)
        if player is None:
            raise UnoValidationError("Você não participa desta partida.")
        return player

    def _require_turn(self, session: UnoSession, user_id: int) -> None:
        self._require_status(session, UnoGameStatus.PLAYING)
        self._require_player(session, user_id)
        current = session.current_player
        if current is None or current.user_id != user_id:
            raise UnoValidationError("Ainda não é sua vez de jogar.")

    async def _record(
        self,
        session: UnoSession,
        user_id: int | None,
        action_type: UnoActionType,
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
