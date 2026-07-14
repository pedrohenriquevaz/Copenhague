from __future__ import annotations

from io import BytesIO
from math import floor

from PIL import Image, ImageDraw, ImageFont

from app.models.casino import (
    BlackjackCard,
    BlackjackOutcome,
    BlackjackSession,
    CardSuit,
)
from app.models.guild_settings import GuildEconomySettings
from app.utils.embeds import format_points

BLACKJACK_TABLE_FILENAME = "blackjack_table.png"

WIDTH = 960
HEIGHT = 640
PANEL = (28, 24, 932, 616)
CARD_WIDTH = 74
CARD_HEIGHT = 104

BG = "#0f0c1f"
PANEL_BG = "#201c31"
PANEL_OUTLINE = "#352e4b"
TEXT = "#f4f1ff"
MUTED = "#bdb6d8"
SUBTLE = "#8f86b0"
CARD_BG = "#f4f1ff"
CARD_BACK = "#e8e2ff"
RED_SUIT = "#b44756"
BLACK_SUIT = "#3b3452"
GREEN = "#1aa36f"
BLUE = "#5663c8"
GOLD = "#d6a84a"
DANGER = "#d95166"


def render_blackjack_table_image(
    session: BlackjackSession,
    settings: GuildEconomySettings,
    *,
    player_display_name: str | None = None,
) -> bytes:
    """Renderiza o painel visual do BlackJack em PNG."""

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    accent = _accent_color(session)
    draw.rounded_rectangle(PANEL, radius=14, fill=PANEL_BG, outline=PANEL_OUTLINE)
    draw.rounded_rectangle(
        (PANEL[0], PANEL[1], PANEL[0] + 8, PANEL[3]),
        radius=10,
        fill=accent,
    )

    _draw_header(draw, session, player_display_name)
    _draw_bet_and_status(draw, session, settings)
    _draw_hand_section(
        draw,
        title=f"Banca ({_dealer_score(session)})",
        cards=session.dealer_hand.cards,
        y=250,
        hidden_card=not session.is_finished and len(session.dealer_hand.cards) == 1,
    )
    _draw_hand_section(
        draw,
        title=f"{player_display_name or 'Você'} ({session.player_hand.value})",
        cards=session.player_hand.cards,
        y=414,
        hidden_card=False,
        player=True,
    )
    _draw_footer(draw, session, settings)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _draw_header(
    draw: ImageDraw.ImageDraw,
    session: BlackjackSession,
    player_display_name: str | None,
) -> None:
    icon_box = (58, 54, 102, 98)
    draw.rounded_rectangle(icon_box, radius=9, fill="#dcecff")
    _draw_club(draw, (80, 76), 11, "#31446b")
    draw.text((116, 56), "Blackjack", font=_font(38, bold=True), fill=TEXT)

    avatar = (798, 52, 884, 138)
    draw.rounded_rectangle(avatar, radius=12, fill="#6d3a3b")
    initials = _initials(player_display_name or "Você")
    initials_font = _font(34, bold=True)
    _draw_centered_text(draw, initials, avatar, initials_font, "#ffe2d8")

    quote = _status_quote(session)
    _draw_wrapped_text(
        draw,
        quote,
        (58, 108),
        max_width=700,
        font=_font(22, italic=True),
        fill="#dad4ef",
        line_gap=6,
    )


def _draw_bet_and_status(
    draw: ImageDraw.ImageDraw,
    session: BlackjackSession,
    settings: GuildEconomySettings,
) -> None:
    y = 170
    chip = (58, y + 2, 82, y + 26)
    draw.ellipse(chip, fill=GOLD)
    draw.ellipse((64, y + 8, 76, y + 20), outline="#fff4c5", width=2)
    draw.text(
        (94, y),
        f"Aposta: {format_points(session.bet, settings.currency_name)}",
        font=_font(24, bold=True),
        fill=TEXT,
    )

    if session.is_finished:
        label = _outcome_text(session)
        fill = _accent_color(session)
    else:
        label = "Mesa em andamento"
        fill = BLUE
    _draw_pill(draw, (58, 205), label, fill)


def _draw_hand_section(
    draw: ImageDraw.ImageDraw,
    *,
    title: str,
    cards: list[BlackjackCard],
    y: int,
    hidden_card: bool,
    player: bool = False,
) -> None:
    badge = (58, y - 8, 94, y + 28)
    draw.rounded_rectangle(badge, radius=8, fill="#f2efff")
    draw.text(
        (67, y - 2),
        "V" if player else "B",
        font=_font(20, bold=True),
        fill=BLUE if player else BLACK_SUIT,
    )
    draw.text((104, y - 8), title, font=_font(26, bold=True), fill=TEXT)

    card_y = y + 42
    visible_cards = list(cards)
    slots = len(visible_cards) + (1 if hidden_card else 0)
    gap = _card_gap(slots)
    x = 58
    for card in visible_cards:
        _draw_card(draw, card, (round(x), card_y))
        x += CARD_WIDTH + gap
    if hidden_card:
        _draw_hidden_card(draw, (round(x), card_y))


def _draw_card(
    draw: ImageDraw.ImageDraw,
    card: BlackjackCard,
    position: tuple[int, int],
) -> None:
    x, y = position
    box = (x, y, x + CARD_WIDTH, y + CARD_HEIGHT)
    draw.rounded_rectangle(box, radius=8, fill=CARD_BG)
    draw.rounded_rectangle(box, radius=8, outline="#d8d1ec", width=2)

    color = (
        RED_SUIT if card.suit in {CardSuit.HEARTS, CardSuit.DIAMONDS} else BLACK_SUIT
    )
    draw.text((x + 10, y + 8), card.display, font=_font(24, bold=True), fill=color)
    _draw_suit(draw, card.suit, (x + CARD_WIDTH // 2, y + 62), 17, color)


def _draw_hidden_card(draw: ImageDraw.ImageDraw, position: tuple[int, int]) -> None:
    x, y = position
    box = (x, y, x + CARD_WIDTH, y + CARD_HEIGHT)
    draw.rounded_rectangle(box, radius=8, fill=CARD_BACK)
    draw.rounded_rectangle(box, radius=8, outline="#d5ccf5", width=2)
    draw.rounded_rectangle(
        (x + 10, y + 10, x + CARD_WIDTH - 10, y + CARD_HEIGHT - 10),
        radius=6,
        outline=BLUE,
        width=3,
    )
    _draw_centered_text(draw, "?", box, _font(40, bold=True), BLUE)


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    session: BlackjackSession,
    settings: GuildEconomySettings,
) -> None:
    y = 565
    draw.text(
        (58, y),
        "Banca para em soft 17 · BlackJack natural paga 2,5x",
        font=_font(18),
        fill=MUTED,
    )
    if not session.is_finished:
        hint = (
            "Dobrar disponível"
            if session.can_double
            else "Dobrar indisponível depois de pedir carta"
        )
        draw.text((58, y + 28), hint, font=_font(18), fill=SUBTLE)
        return

    x = 58
    payout = format_points(session.payout, settings.currency_name)
    _draw_pill(draw, (x, y + 30), f"Pagamento: {payout}", _accent_color(session))
    x += 260
    if session.cashback > 0:
        cashback = format_points(session.cashback, settings.currency_name)
        _draw_pill(draw, (x, y + 30), f"Cashback: {cashback}", BLUE)
        x += 250
    if session.win_streak > 1:
        _draw_pill(draw, (x, y + 30), f"Sequência: {session.win_streak}", GOLD)


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    fill: str,
) -> None:
    x, y = position
    font = _font(17, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + 28
    height = 34
    draw.rounded_rectangle((x, y, x + width, y + height), radius=9, fill=fill)
    draw.text((x + 14, y + 7), text, font=font, fill="#ffffff")


def _draw_suit(
    draw: ImageDraw.ImageDraw,
    suit: CardSuit,
    center: tuple[int, int],
    size: int,
    fill: str,
) -> None:
    if suit is CardSuit.DIAMONDS:
        x, y = center
        draw.polygon(
            [(x, y - size), (x + size, y), (x, y + size), (x - size, y)],
            fill=fill,
        )
        return
    if suit is CardSuit.HEARTS:
        _draw_heart(draw, center, size, fill)
        return
    if suit is CardSuit.CLUBS:
        _draw_club(draw, center, size, fill)
        return
    _draw_spade(draw, center, size, fill)


def _draw_heart(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    size: int,
    fill: str,
) -> None:
    x, y = center
    r = floor(size * 0.58)
    draw.ellipse((x - r - 7, y - r, x + 1, y + 8), fill=fill)
    draw.ellipse((x - 1, y - r, x + r + 7, y + 8), fill=fill)
    draw.polygon([(x - size, y + 2), (x + size, y + 2), (x, y + size + 8)], fill=fill)


def _draw_club(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    size: int,
    fill: str,
) -> None:
    x, y = center
    r = floor(size * 0.55)
    draw.ellipse((x - r, y - size, x + r, y - size + 2 * r), fill=fill)
    draw.ellipse((x - size, y - r // 2, x - size + 2 * r, y + r + 5), fill=fill)
    draw.ellipse((x + size - 2 * r, y - r // 2, x + size, y + r + 5), fill=fill)
    draw.polygon(
        [(x - 5, y + 8), (x + 5, y + 8), (x + 8, y + size), (x - 8, y + size)],
        fill=fill,
    )


def _draw_spade(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    size: int,
    fill: str,
) -> None:
    x, y = center
    r = floor(size * 0.58)
    draw.ellipse((x - r - 7, y - 4, x + 1, y + r + 5), fill=fill)
    draw.ellipse((x - 1, y - 4, x + r + 7, y + r + 5), fill=fill)
    draw.polygon([(x - size, y + 5), (x + size, y + 5), (x, y - size - 8)], fill=fill)
    draw.polygon(
        [(x - 5, y + 12), (x + 5, y + 12), (x + 8, y + size), (x - 8, y + size)],
        fill=fill,
    )


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = box[0] + (box[2] - box[0] - width) / 2
    y = box[1] + (box[3] - box[1] - height) / 2 - 2
    draw.text((x, y), text, font=font, fill=fill)


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: tuple[int, int],
    *,
    max_width: int,
    font: ImageFont.ImageFont,
    fill: str,
    line_gap: int = 4,
) -> None:
    x, y = position
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            line = candidate
            continue
        draw.text((x, y), line, font=font, fill=fill)
        y += _line_height(draw, font) + line_gap
        line = word
    if line:
        draw.text((x, y), line, font=font, fill=fill)


def _line_height(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    return bbox[3] - bbox[1]


def _font(
    size: int,
    *,
    bold: bool = False,
    italic: bool = False,
) -> ImageFont.ImageFont:
    if bold and italic:
        suffix = "BoldOblique"
    elif bold:
        suffix = "Bold"
    elif italic:
        suffix = "Oblique"
    else:
        suffix = ""
    candidates = []
    if suffix:
        candidates.append(f"DejaVuSans-{suffix}.ttf")
    candidates.extend(
        [
            "DejaVuSans.ttf",
            "Arial Bold.ttf" if bold else "Arial Italic.ttf" if italic else "Arial.ttf",
            "arialbd.ttf" if bold else "ariali.ttf" if italic else "arial.ttf",
            "segoeuib.ttf" if bold else "segoeuii.ttf" if italic else "segoeui.ttf",
        ]
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _card_gap(slots: int) -> float:
    if slots <= 1:
        return 12
    max_width = 620
    total_cards = slots * CARD_WIDTH
    if total_cards <= max_width:
        return 12
    return max(4, (max_width - total_cards) / (slots - 1))


def _dealer_score(session: BlackjackSession) -> str:
    if not session.is_finished and len(session.dealer_hand.cards) == 1:
        return f"{session.dealer_hand.value}+?"
    return str(session.dealer_hand.value)


def _outcome_text(session: BlackjackSession) -> str:
    if session.outcome is BlackjackOutcome.PLAYER_BLACKJACK:
        return "BlackJack natural"
    if session.outcome is BlackjackOutcome.PLAYER_WIN:
        return "Você venceu"
    if session.outcome is BlackjackOutcome.PUSH:
        return "Empate"
    if session.outcome is BlackjackOutcome.PLAYER_BUST:
        return "Você estourou"
    if session.outcome is BlackjackOutcome.DEALER_BLACKJACK:
        return "BlackJack da banca"
    if session.outcome is BlackjackOutcome.EXPIRED:
        return "Partida expirada"
    return "Banca venceu"


def _status_quote(session: BlackjackSession) -> str:
    if not session.is_finished:
        if session.can_double:
            return "Mesa aberta. Você ainda pode dobrar nesta mão."
        if session.player_hand.value == 21:
            return "Vinte e um cravado. Agora é com a banca."
        return "Escolha sua próxima jogada."
    if session.outcome is BlackjackOutcome.PLAYER_BLACKJACK:
        return "Natural bonito. Essa mão veio pronta."
    if session.outcome is BlackjackOutcome.PLAYER_WIN:
        return "Boa mão. Você venceu a banca."
    if session.outcome is BlackjackOutcome.PUSH:
        return "Empate limpo. A aposta voltou para você."
    if session.outcome is BlackjackOutcome.PLAYER_BUST:
        return "Passou de 21. A mesa cobrou a ousadia."
    if session.outcome is BlackjackOutcome.DEALER_BLACKJACK:
        return "A banca abriu BlackJack natural."
    if session.outcome is BlackjackOutcome.EXPIRED:
        return "A mesa esfriou e a partida foi encerrada."
    return "A banca levou essa mão."


def _accent_color(session: BlackjackSession) -> str:
    if not session.is_finished:
        return BLUE
    if session.outcome in {
        BlackjackOutcome.PLAYER_BLACKJACK,
        BlackjackOutcome.PLAYER_WIN,
    }:
        return GREEN
    if session.outcome is BlackjackOutcome.PUSH:
        return BLUE
    return DANGER


def _initials(name: str) -> str:
    parts = [part for part in name.replace("_", " ").split() if part]
    if not parts:
        return "BJ"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()
