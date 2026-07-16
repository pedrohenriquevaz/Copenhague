from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class TrucoTeam(StrEnum):
    """Times de uma partida de Truco 2x2."""

    BLUE = "blue"
    RED = "red"

    @property
    def opponent(self) -> TrucoTeam:
        return TrucoTeam.RED if self is TrucoTeam.BLUE else TrucoTeam.BLUE


class TrucoGameStatus(StrEnum):
    """Estado geral de uma partida de Truco."""

    LOBBY = "LOBBY"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class TrucoGameMode(StrEnum):
    PVP = "PVP"
    PVE = "PVE"


class TrucoActionType(StrEnum):
    """Acoes auditaveis de uma partida de Truco."""

    CREATE = "CREATE"
    ACCEPT = "ACCEPT"
    DECLINE = "DECLINE"
    START = "START"
    PLAY_CARD = "PLAY_CARD"
    REQUEST_TRUCO = "REQUEST_TRUCO"
    ACCEPT_TRUCO = "ACCEPT_TRUCO"
    RUN = "RUN"
    RAISE_TRUCO = "RAISE_TRUCO"
    FINISH_HAND = "FINISH_HAND"
    FINISH_GAME = "FINISH_GAME"
    CANCEL = "CANCEL"


class TrucoSuit(StrEnum):
    """Naipes do baralho espanhol usado no Truco Paulista."""

    OUROS = "ouros"
    ESPADAS = "espadas"
    COPAS = "copas"
    BASTOS = "bastos"


class TrucoRank(StrEnum):
    """Cartas do baralho espanhol de 40 cartas."""

    ACE = "A"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    SOTA = "S"
    CAVALO = "C"
    REI = "R"


TRUCO_RANK_ORDER: tuple[TrucoRank, ...] = (
    TrucoRank.FOUR,
    TrucoRank.FIVE,
    TrucoRank.SIX,
    TrucoRank.SEVEN,
    TrucoRank.SOTA,
    TrucoRank.CAVALO,
    TrucoRank.REI,
    TrucoRank.ACE,
    TrucoRank.TWO,
    TrucoRank.THREE,
)

TRUCO_SUIT_POWER: dict[TrucoSuit, int] = {
    TrucoSuit.OUROS: 0,
    TrucoSuit.ESPADAS: 1,
    TrucoSuit.COPAS: 2,
    TrucoSuit.BASTOS: 3,
}

TRUCO_VALUES: tuple[int, ...] = (1, 3, 6, 9, 12)


@dataclass(frozen=True, slots=True)
class TrucoCard:
    """Carta do Truco."""

    rank: TrucoRank
    suit: TrucoSuit

    @property
    def code(self) -> str:
        return f"{self.rank.value}:{self.suit.value}"

    @property
    def label(self) -> str:
        return f"{self.rank_name} de {self.suit_label}"

    @property
    def short_label(self) -> str:
        return f"{self.rank_label}{self.suit_symbol}"

    @property
    def rank_label(self) -> str:
        labels = {
            TrucoRank.ACE: "A",
            TrucoRank.SOTA: "J",
            TrucoRank.CAVALO: "Q",
            TrucoRank.REI: "K",
        }
        return labels.get(self.rank, self.rank.value)

    @property
    def rank_name(self) -> str:
        return {
            TrucoRank.SOTA: "Valete",
            TrucoRank.CAVALO: "Rainha",
            TrucoRank.REI: "Rei",
        }.get(self.rank, self.rank_label)

    @property
    def suit_label(self) -> str:
        labels = {
            TrucoSuit.OUROS: "Ouros",
            TrucoSuit.ESPADAS: "Espadas",
            TrucoSuit.COPAS: "Copas",
            TrucoSuit.BASTOS: "Bastos",
        }
        return labels[self.suit]

    @property
    def suit_symbol(self) -> str:
        symbols = {
            TrucoSuit.OUROS: "♦",
            TrucoSuit.ESPADAS: "♠",
            TrucoSuit.COPAS: "♥",
            TrucoSuit.BASTOS: "♣",
        }
        return symbols[self.suit]

    def to_json(self) -> str:
        return self.code

    @classmethod
    def from_json(cls, value: str) -> TrucoCard:
        rank, suit = value.split(":", 1)
        return cls(rank=TrucoRank(rank), suit=TrucoSuit(suit))


@dataclass(slots=True)
class TrucoPlayer:
    user_id: int
    team: TrucoTeam
    seat_position: int
    accepted: bool = False
    is_bot: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "team": self.team.value,
            "seat_position": self.seat_position,
            "accepted": self.accepted,
            "is_bot": self.is_bot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrucoPlayer:
        return cls(
            user_id=int(data["user_id"]),
            team=TrucoTeam(str(data["team"])),
            seat_position=int(data["seat_position"]),
            accepted=bool(data.get("accepted", False)),
            is_bot=bool(data.get("is_bot", False)),
        )


@dataclass(slots=True)
class TrucoPlayedCard:
    user_id: int
    card: TrucoCard
    round_number: int
    play_order: int
    is_closed: bool
    played_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "card": self.card.to_json(),
            "round_number": self.round_number,
            "play_order": self.play_order,
            "is_closed": self.is_closed,
            "played_at": self.played_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrucoPlayedCard:
        return cls(
            user_id=int(data["user_id"]),
            card=TrucoCard.from_json(str(data["card"])),
            round_number=int(data["round_number"]),
            play_order=int(data["play_order"]),
            is_closed=bool(data["is_closed"]),
            played_at=datetime.fromisoformat(str(data["played_at"])),
        )


@dataclass(slots=True)
class TrucoRoundReveal:
    """Retrato imutável da última rodada para a apresentação da mesa."""

    hand_number: int
    round_number: int
    hand_value: int
    cards: list[TrucoPlayedCard]
    winner: TrucoTeam | None
    winner_user_id: int | None
    score_blue_before: int
    score_red_before: int
    round_wins_blue: int
    round_wins_red: int
    vira: TrucoCard | None
    manilha_rank: TrucoRank | None

    @property
    def key(self) -> str:
        return f"{self.hand_number}:{self.round_number}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hand_number": self.hand_number,
            "round_number": self.round_number,
            "hand_value": self.hand_value,
            "cards": [played.to_dict() for played in self.cards],
            "winner": self.winner.value if self.winner is not None else None,
            "winner_user_id": self.winner_user_id,
            "score_blue_before": self.score_blue_before,
            "score_red_before": self.score_red_before,
            "round_wins_blue": self.round_wins_blue,
            "round_wins_red": self.round_wins_red,
            "vira": self.vira.to_json() if self.vira else None,
            "manilha_rank": self.manilha_rank.value if self.manilha_rank else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TrucoRoundReveal | None:
        if not data:
            return None
        return cls(
            hand_number=int(data["hand_number"]),
            round_number=int(data["round_number"]),
            hand_value=int(data.get("hand_value", 1)),
            cards=[
                TrucoPlayedCard.from_dict(played) for played in data.get("cards", [])
            ],
            winner=(
                TrucoTeam(str(data["winner"]))
                if data.get("winner") is not None
                else None
            ),
            winner_user_id=(
                int(data["winner_user_id"])
                if data.get("winner_user_id") is not None
                else None
            ),
            score_blue_before=int(data.get("score_blue_before", 0)),
            score_red_before=int(data.get("score_red_before", 0)),
            round_wins_blue=int(data.get("round_wins_blue", 0)),
            round_wins_red=int(data.get("round_wins_red", 0)),
            vira=(
                TrucoCard.from_json(str(data["vira"]))
                if data.get("vira") is not None
                else None
            ),
            manilha_rank=(
                TrucoRank(str(data["manilha_rank"]))
                if data.get("manilha_rank") is not None
                else None
            ),
        )


@dataclass(slots=True)
class TrucoChallenge:
    requested_by: int
    requesting_team: TrucoTeam
    target_team: TrucoTeam
    current_value: int
    proposed_value: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_by": self.requested_by,
            "requesting_team": self.requesting_team.value,
            "target_team": self.target_team.value,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TrucoChallenge | None:
        if not data:
            return None
        return cls(
            requested_by=int(data["requested_by"]),
            requesting_team=TrucoTeam(str(data["requesting_team"])),
            target_team=TrucoTeam(str(data["target_team"])),
            current_value=int(data["current_value"]),
            proposed_value=int(data["proposed_value"]),
        )


@dataclass(slots=True)
class TrucoSession:
    """Estado oficial de uma partida de Truco."""

    id: int | None
    guild_id: int
    channel_id: int
    message_id: int | None
    created_by: int
    stake: int
    status: TrucoGameStatus
    players: list[TrucoPlayer]
    economic_policy_snapshots: dict[int, dict[str, Any]] = field(default_factory=dict)
    game_mode: TrucoGameMode = TrucoGameMode.PVP
    score_blue: int = 0
    score_red: int = 0
    hand_value: int = 1
    hand_number: int = 1
    round_number: int = 1
    hand_starter_position: int = 0
    round_starter_position: int = 0
    current_turn_user_id: int | None = None
    vira: TrucoCard | None = None
    manilha_rank: TrucoRank | None = None
    hands: dict[int, list[TrucoCard]] = field(default_factory=dict)
    round_winners: list[TrucoTeam | None] = field(default_factory=list)
    played_cards: list[TrucoPlayedCard] = field(default_factory=list)
    last_round_reveal: TrucoRoundReveal | None = None
    round_reveal_pending: bool = False
    pending_challenge: TrucoChallenge | None = None
    is_escurona: bool = False
    winning_team: TrucoTeam | None = None
    zero_loss_announcement: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def player_ids(self) -> list[int]:
        return [player.user_id for player in sorted(self.players, key=_player_seat)]

    @property
    def accepted_user_ids(self) -> set[int]:
        return {player.user_id for player in self.players if player.accepted}

    @property
    def all_accepted(self) -> bool:
        return all(player.accepted for player in self.players)

    @property
    def pot(self) -> int:
        return self.stake * sum(not player.is_bot for player in self.players)

    @property
    def expected_payout_per_winner(self) -> int:
        if self.game_mode is TrucoGameMode.PVE:
            if self.winning_team is not None and all(
                player.is_bot for player in self.team_players(self.winning_team)
            ):
                return 0
            return self.stake * 2
        winners = max(1, len(self.team_players(self.winning_team or TrucoTeam.BLUE)))
        return (self.pot * 125 // 100) // winners

    def player(self, user_id: int) -> TrucoPlayer | None:
        return next(
            (player for player in self.players if player.user_id == user_id),
            None,
        )

    def team_players(self, team: TrucoTeam) -> list[TrucoPlayer]:
        return sorted(
            [player for player in self.players if player.team is team],
            key=_player_seat,
        )

    def score(self, team: TrucoTeam) -> int:
        return self.score_blue if team is TrucoTeam.BLUE else self.score_red

    def set_score(self, team: TrucoTeam, value: int) -> None:
        if team is TrucoTeam.BLUE:
            self.score_blue = value
        else:
            self.score_red = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "created_by": self.created_by,
            "stake": self.stake,
            "status": self.status.value,
            "players": [player.to_dict() for player in self.players],
            "economic_policy_snapshots": {
                str(user_id): snapshot
                for user_id, snapshot in self.economic_policy_snapshots.items()
            },
            "game_mode": self.game_mode.value,
            "score_blue": self.score_blue,
            "score_red": self.score_red,
            "hand_value": self.hand_value,
            "hand_number": self.hand_number,
            "round_number": self.round_number,
            "hand_starter_position": self.hand_starter_position,
            "round_starter_position": self.round_starter_position,
            "current_turn_user_id": self.current_turn_user_id,
            "vira": self.vira.to_json() if self.vira else None,
            "manilha_rank": self.manilha_rank.value if self.manilha_rank else None,
            "hands": {
                str(user_id): [card.to_json() for card in cards]
                for user_id, cards in self.hands.items()
            },
            "round_winners": [
                winner.value if winner is not None else None
                for winner in self.round_winners
            ],
            "played_cards": [played.to_dict() for played in self.played_cards],
            "last_round_reveal": (
                self.last_round_reveal.to_dict()
                if self.last_round_reveal is not None
                else None
            ),
            "round_reveal_pending": self.round_reveal_pending,
            "pending_challenge": (
                self.pending_challenge.to_dict()
                if self.pending_challenge is not None
                else None
            ),
            "is_escurona": self.is_escurona,
            "winning_team": self.winning_team.value if self.winning_team else None,
            "zero_loss_announcement": self.zero_loss_announcement,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrucoSession:
        return cls(
            id=int(data["id"]) if data.get("id") is not None else None,
            guild_id=int(data["guild_id"]),
            channel_id=int(data["channel_id"]),
            message_id=(
                int(data["message_id"]) if data.get("message_id") is not None else None
            ),
            created_by=int(data["created_by"]),
            stake=int(data["stake"]),
            status=TrucoGameStatus(str(data["status"])),
            players=[
                TrucoPlayer.from_dict(player_data)
                for player_data in data.get("players", [])
            ],
            economic_policy_snapshots={
                int(user_id): dict(snapshot)
                for user_id, snapshot in data.get(
                    "economic_policy_snapshots", {}
                ).items()
            },
            game_mode=TrucoGameMode(str(data.get("game_mode", "PVP"))),
            score_blue=int(data.get("score_blue", 0)),
            score_red=int(data.get("score_red", 0)),
            hand_value=int(data.get("hand_value", 1)),
            hand_number=int(data.get("hand_number", 1)),
            round_number=int(data.get("round_number", 1)),
            hand_starter_position=int(
                data.get("hand_starter_position", data.get("starter_position", 0))
            ),
            round_starter_position=int(
                data.get("round_starter_position", data.get("starter_position", 0))
            ),
            current_turn_user_id=(
                int(data["current_turn_user_id"])
                if data.get("current_turn_user_id") is not None
                else None
            ),
            vira=(
                TrucoCard.from_json(str(data["vira"]))
                if data.get("vira") is not None
                else None
            ),
            manilha_rank=(
                TrucoRank(str(data["manilha_rank"]))
                if data.get("manilha_rank") is not None
                else None
            ),
            hands={
                int(user_id): [TrucoCard.from_json(card) for card in cards]
                for user_id, cards in data.get("hands", {}).items()
            },
            round_winners=[
                TrucoTeam(str(winner)) if winner is not None else None
                for winner in data.get("round_winners", [])
            ],
            played_cards=[
                TrucoPlayedCard.from_dict(played)
                for played in data.get("played_cards", [])
            ],
            last_round_reveal=TrucoRoundReveal.from_dict(data.get("last_round_reveal")),
            round_reveal_pending=bool(data.get("round_reveal_pending", False)),
            pending_challenge=TrucoChallenge.from_dict(data.get("pending_challenge")),
            is_escurona=bool(data.get("is_escurona", False)),
            winning_team=(
                TrucoTeam(str(data["winning_team"]))
                if data.get("winning_team") is not None
                else None
            ),
            zero_loss_announcement=data.get("zero_loss_announcement"),
            created_at=_parse_optional_datetime(data.get("created_at")),
            updated_at=_parse_optional_datetime(data.get("updated_at")),
            finished_at=_parse_optional_datetime(data.get("finished_at")),
        )


def _player_seat(player: TrucoPlayer) -> int:
    return player.seat_position


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))
