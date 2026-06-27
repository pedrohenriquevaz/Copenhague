from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CardSuit(StrEnum):
    """Naipes usados no baralho do cassino."""

    SPADES = "S"
    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"


class CardRank(StrEnum):
    """Valores das cartas do BlackJack."""

    ACE = "A"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"


class BlackjackOutcome(StrEnum):
    """Resultado final de uma partida."""

    PLAYER_BLACKJACK = "PLAYER_BLACKJACK"
    PLAYER_WIN = "PLAYER_WIN"
    DEALER_WIN = "DEALER_WIN"
    PUSH = "PUSH"
    PLAYER_BUST = "PLAYER_BUST"
    DEALER_BLACKJACK = "DEALER_BLACKJACK"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class BlackjackCard:
    """Carta de BlackJack."""

    rank: CardRank
    suit: CardSuit

    @property
    def display(self) -> str:
        return self.rank.value

    @property
    def base_value(self) -> int:
        if self.rank is CardRank.ACE:
            return 11
        if self.rank in {CardRank.JACK, CardRank.QUEEN, CardRank.KING}:
            return 10
        return int(self.rank.value)


@dataclass(slots=True)
class BlackjackHand:
    """Mao de cartas com pontuacao flexivel para ases."""

    cards: list[BlackjackCard] = field(default_factory=list)

    @property
    def value(self) -> int:
        total = sum(card.base_value for card in self.cards)
        aces = sum(1 for card in self.cards if card.rank is CardRank.ACE)
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total

    @property
    def is_blackjack(self) -> bool:
        return len(self.cards) == 2 and self.value == 21

    @property
    def is_bust(self) -> bool:
        return self.value > 21

    def add(self, card: BlackjackCard) -> None:
        self.cards.append(card)


@dataclass(slots=True)
class BlackjackSession:
    """Estado em memoria de uma partida ativa ou finalizada."""

    guild_id: int
    user_id: int
    bet: int
    deck: list[BlackjackCard]
    player_hand: BlackjackHand = field(default_factory=BlackjackHand)
    dealer_hand: BlackjackHand = field(default_factory=BlackjackHand)
    outcome: BlackjackOutcome | None = None
    payout: int = 0
    can_double: bool = True

    @property
    def is_finished(self) -> bool:
        return self.outcome is not None
