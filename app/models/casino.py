from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.models.economy import UserWallet


class CasinoGameType(StrEnum):
    """Jogos do arcade de pontos virtuais."""

    COIN_FLIP = "coin_flip"
    DICE = "dice"
    SLOT = "slot"
    ROULETTE = "roulette"
    DUEL = "duel"
    MASCOT_RACE = "mascot_race"
    BLACKJACK = "blackjack"


class CasinoOutcome(StrEnum):
    """Resultado normalizado de jogos instantaneos."""

    WON = "WON"
    LOST = "LOST"
    DRAW = "DRAW"


class CoinSide(StrEnum):
    """Escolhas do Cara ou Coroa."""

    CARA = "cara"
    COROA = "coroa"


class DiceMode(StrEnum):
    """Modos do jogo de dados."""

    NUMERO = "numero"
    PAR = "par"
    IMPAR = "impar"
    MAIOR = "maior"
    MENOR = "menor"


class RouletteColor(StrEnum):
    """Cores da roleta simplificada."""

    VERMELHO = "vermelho"
    PRETO = "preto"
    VERDE = "verde"


class DuelMode(StrEnum):
    """Modos iniciais do duelo entre usuarios."""

    SORTE = "sorte"
    DADOS = "dados"


class RaceMascot(StrEnum):
    """Mascotes da corrida individual."""

    DRAGAO = "dragao"
    LOBO = "lobo"
    RAPOSA = "raposa"
    TARTARUGA = "tartaruga"
    AGUIA = "aguia"
    GATO = "gato"


@dataclass(frozen=True, slots=True)
class SlotSymbol:
    """Simbolo de slot machine."""

    key: str
    label: str
    triple_multiplier: int


@dataclass(slots=True)
class CasinoGameResult:
    """Resultado financeiro e visual de um jogo instantaneo."""

    guild_id: int
    user_id: int
    game_type: CasinoGameType
    bet: int
    payout: int
    profit: int
    outcome: CasinoOutcome
    title: str
    result_label: str
    detail_lines: list[str]
    wallet: UserWallet


@dataclass(slots=True)
class DuelResult:
    """Resultado de um duelo entre dois usuarios."""

    guild_id: int
    challenger_id: int
    challenged_id: int
    mode: DuelMode
    bet: int
    winner_id: int | None
    payout: int
    outcome: CasinoOutcome
    result_label: str
    detail_lines: list[str]
    challenger_wallet: UserWallet
    challenged_wallet: UserWallet


@dataclass(slots=True)
class CasinoUserStats:
    """Resumo agregado simples de jogos por usuario."""

    guild_id: int
    user_id: int
    total_games_played: int
    total_bet_amount: int
    total_payout_amount: int
    net_profit: int
    biggest_win: int
    biggest_loss: int


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
    base_payout: int = 0
    streak_bonus: int = 0
    win_streak: int = 0
    payout_multiplier_percent: int = 100
    can_double: bool = True

    @property
    def is_finished(self) -> bool:
        return self.outcome is not None
