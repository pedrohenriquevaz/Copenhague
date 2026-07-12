from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class UnoColor(StrEnum):
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"

    @property
    def label(self) -> str:
        return {
            UnoColor.RED: "Vermelho",
            UnoColor.BLUE: "Azul",
            UnoColor.GREEN: "Verde",
            UnoColor.YELLOW: "Amarelo",
        }[self]

    @property
    def symbol(self) -> str:
        return {
            UnoColor.RED: "🔴",
            UnoColor.BLUE: "🔵",
            UnoColor.GREEN: "🟢",
            UnoColor.YELLOW: "🟡",
        }[self]


class UnoValue(StrEnum):
    ZERO = "0"
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    SKIP = "skip"
    REVERSE = "reverse"
    DRAW_TWO = "draw_two"
    WILD = "wild"
    WILD_DRAW_FOUR = "wild_draw_four"

    @property
    def label(self) -> str:
        return {
            UnoValue.SKIP: "Bloqueio",
            UnoValue.REVERSE: "Inverter",
            UnoValue.DRAW_TWO: "+2",
            UnoValue.WILD: "Troca de cor",
            UnoValue.WILD_DRAW_FOUR: "+4",
        }.get(self, self.value)

    @property
    def is_wild(self) -> bool:
        return self in {UnoValue.WILD, UnoValue.WILD_DRAW_FOUR}


class UnoGameStatus(StrEnum):
    LOBBY = "LOBBY"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class UnoGameMode(StrEnum):
    PVP = "PVP"
    PVE = "PVE"


class UnoActionType(StrEnum):
    CREATE = "CREATE"
    JOIN = "JOIN"
    LEAVE = "LEAVE"
    START = "START"
    PLAY_CARD = "PLAY_CARD"
    DRAW_CARD = "DRAW_CARD"
    PASS = "PASS"
    CANCEL = "CANCEL"
    FINISH = "FINISH"


@dataclass(frozen=True, slots=True)
class UnoCard:
    id: int
    color: UnoColor | None
    value: UnoValue

    @property
    def label(self) -> str:
        if self.color is None:
            return self.value.label
        return f"{self.color.label} {self.value.label}"

    @property
    def short_label(self) -> str:
        color = self.color.symbol if self.color else "🌈"
        return f"{color} {self.value.label}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "color": self.color.value if self.color else None,
            "value": self.value.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnoCard:
        color = data.get("color")
        return cls(
            id=int(data["id"]),
            color=UnoColor(str(color)) if color is not None else None,
            value=UnoValue(str(data["value"])),
        )


@dataclass(slots=True)
class UnoPlayer:
    user_id: int
    hand: list[UnoCard] = field(default_factory=list)
    is_bot: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "hand": [card.to_dict() for card in self.hand],
            "is_bot": self.is_bot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnoPlayer:
        return cls(
            user_id=int(data["user_id"]),
            hand=[UnoCard.from_dict(card) for card in data.get("hand", [])],
            is_bot=bool(data.get("is_bot", False)),
        )


@dataclass(slots=True)
class UnoSession:
    id: int | None
    guild_id: int
    channel_id: int
    message_id: int | None
    title: str
    created_by: int
    status: UnoGameStatus
    players: list[UnoPlayer]
    stake: int = 0
    game_mode: UnoGameMode = UnoGameMode.PVP
    stakes_debited: bool = False
    draw_pile: list[UnoCard] = field(default_factory=list)
    discard_pile: list[UnoCard] = field(default_factory=list)
    current_player_index: int = 0
    direction: int = 1
    current_color: UnoColor | None = None
    last_action: str = "Aguardando jogadores."
    drawn_card_id: int | None = None
    winner_user_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def player_ids(self) -> list[int]:
        return [player.user_id for player in self.players]

    @property
    def human_players(self) -> list[UnoPlayer]:
        return [player for player in self.players if not player.is_bot]

    @property
    def pot(self) -> int:
        return self.stake * len(self.human_players)

    @property
    def expected_winner_payout(self) -> int:
        if self.game_mode is UnoGameMode.PVE:
            return self.stake * 2
        return self.pot * 125 // 100

    @property
    def current_player(self) -> UnoPlayer | None:
        if self.status is not UnoGameStatus.PLAYING or not self.players:
            return None
        return self.players[self.current_player_index % len(self.players)]

    @property
    def top_card(self) -> UnoCard | None:
        return self.discard_pile[-1] if self.discard_pile else None

    def player(self, user_id: int) -> UnoPlayer | None:
        return next(
            (player for player in self.players if player.user_id == user_id),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "title": self.title,
            "created_by": self.created_by,
            "status": self.status.value,
            "players": [player.to_dict() for player in self.players],
            "stake": self.stake,
            "game_mode": self.game_mode.value,
            "stakes_debited": self.stakes_debited,
            "draw_pile": [card.to_dict() for card in self.draw_pile],
            "discard_pile": [card.to_dict() for card in self.discard_pile],
            "current_player_index": self.current_player_index,
            "direction": self.direction,
            "current_color": self.current_color.value if self.current_color else None,
            "last_action": self.last_action,
            "drawn_card_id": self.drawn_card_id,
            "winner_user_id": self.winner_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnoSession:
        current_color = data.get("current_color")
        return cls(
            id=int(data["id"]) if data.get("id") is not None else None,
            guild_id=int(data["guild_id"]),
            channel_id=int(data["channel_id"]),
            message_id=(
                int(data["message_id"]) if data.get("message_id") is not None else None
            ),
            title=str(data["title"]),
            created_by=int(data["created_by"]),
            status=UnoGameStatus(str(data["status"])),
            players=[UnoPlayer.from_dict(item) for item in data.get("players", [])],
            stake=int(data.get("stake", 0)),
            game_mode=UnoGameMode(str(data.get("game_mode", "PVP"))),
            stakes_debited=bool(data.get("stakes_debited", False)),
            draw_pile=[UnoCard.from_dict(item) for item in data.get("draw_pile", [])],
            discard_pile=[
                UnoCard.from_dict(item) for item in data.get("discard_pile", [])
            ],
            current_player_index=int(data.get("current_player_index", 0)),
            direction=int(data.get("direction", 1)),
            current_color=(
                UnoColor(str(current_color)) if current_color is not None else None
            ),
            last_action=str(data.get("last_action", "")),
            drawn_card_id=(
                int(data["drawn_card_id"])
                if data.get("drawn_card_id") is not None
                else None
            ),
            winner_user_id=(
                int(data["winner_user_id"])
                if data.get("winner_user_id") is not None
                else None
            ),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
            finished_at=_parse_datetime(data.get("finished_at")),
        )


def _parse_datetime(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None
