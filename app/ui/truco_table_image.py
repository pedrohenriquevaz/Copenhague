from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.models.guild_settings import GuildEconomySettings
from app.models.truco import (
    TrucoCard,
    TrucoGameStatus,
    TrucoPlayedCard,
    TrucoSession,
    TrucoSuit,
    TrucoTeam,
)
from app.utils.embeds import format_points

TRUCO_TABLE_FILENAME = "truco_table.png"

WIDTH = 960
HEIGHT = 640

BACKGROUND = "#2e7c55"
PANEL = "#171d19"
TABLE = "#17432f"
TABLE_INNER = "#1b4d36"
TABLE_LINE = "#3f765d"
TEXT = "#f3f6f4"
MUTED = "#aebbb3"
SUBTLE = "#718078"
BLUE = "#4d8fa3"
RED = "#b56c62"
GOLD = "#d6b867"
CARD = "#f4f1e9"
CARD_LINE = "#d7d2c7"
CARD_DARK = "#26302b"
CARD_RED = "#a84444"
CARD_BLACK = "#252b28"

CARD_WIDTH = 62
CARD_HEIGHT = 88


def render_truco_table_image(
    session: TrucoSession,
    settings: GuildEconomySettings,
    *,
    display_names: dict[int, str] | None = None,
    reveal_round: bool = False,
) -> bytes:
    """Renderiza a mesa publica de Truco em PNG, sem revelar maos privadas."""

    names = display_names or {}
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 942, 622), radius=14, fill=PANEL)

    showing_reveal = reveal_round and session.last_round_reveal is not None
    _draw_header(draw, session, settings, reveal_round=showing_reveal)
    _draw_table(draw)
    _draw_players(draw, session, names, reveal_round=showing_reveal)

    if showing_reveal:
        _draw_playing_state(draw, session, names, reveal_round=True)
    elif session.status is TrucoGameStatus.LOBBY:
        _draw_lobby(draw, session)
    elif session.status is TrucoGameStatus.PLAYING:
        _draw_playing_state(draw, session, names)
    elif session.status is TrucoGameStatus.FINISHED:
        _draw_finished(draw, session)
    else:
        _draw_center_notice(draw, "Mesa cancelada", MUTED)

    output = BytesIO()
    image.save(output, format="PNG", compress_level=6)
    return output.getvalue()


def _draw_header(
    draw: ImageDraw.ImageDraw,
    session: TrucoSession,
    settings: GuildEconomySettings,
    *,
    reveal_round: bool = False,
) -> None:
    draw.text((42, 35), "TRUCO PAULISTA", font=_font(25, bold=True), fill=TEXT)
    draw.text((42, 67), _status_label(session), font=_font(15), fill=MUTED)

    score_font = _font(34, bold=True)
    reveal = session.last_round_reveal if reveal_round else None
    score_blue = reveal.score_blue_before if reveal else session.score_blue
    score_red = reveal.score_red_before if reveal else session.score_red
    score = f"{score_blue}  -  {score_red}"
    score_width = draw.textlength(score, font=score_font)
    draw.text(((WIDTH - score_width) / 2, 31), score, font=score_font, fill=TEXT)
    _draw_team_mark(draw, 398, 76, "AZUL", BLUE)
    _draw_team_mark(draw, 506, 76, "VERMELHA", RED)

    stake = format_points(session.stake, settings.currency_name)
    pot = format_points(session.pot, settings.currency_name)
    right_x = 918
    _draw_right_text(draw, right_x, 39, f"Aposta  {stake}", _font(16, bold=True), TEXT)
    _draw_right_text(draw, right_x, 65, f"Pote  {pot}", _font(15), MUTED)


def _draw_table(draw: ImageDraw.ImageDraw) -> None:
    outer = (116, 115, 844, 574)
    inner = (137, 136, 823, 553)
    draw.ellipse(outer, fill="#102b20", outline=TABLE_LINE, width=3)
    draw.ellipse(inner, fill=TABLE_INNER, outline=TABLE, width=4)
    draw.ellipse((188, 178, 772, 511), outline="#2c674b", width=2)


def _draw_players(
    draw: ImageDraw.ImageDraw,
    session: TrucoSession,
    names: dict[int, str],
    *,
    reveal_round: bool = False,
) -> None:
    boxes = (
        {
            0: (330, 532, 630, 600),
            1: (330, 102, 630, 170),
        }
        if len(session.players) == 2
        else {
            0: (330, 532, 630, 600),
            1: (30, 280, 253, 348),
            2: (330, 102, 630, 170),
            3: (707, 280, 930, 348),
        }
    )
    for player in sorted(session.players, key=lambda item: item.seat_position):
        box = boxes[player.seat_position]
        accent = BLUE if player.team is TrucoTeam.BLUE else RED
        current = (
            not reveal_round
            and session.status is TrucoGameStatus.PLAYING
            and session.current_turn_user_id == player.user_id
        )
        outline = GOLD if current else accent
        width = 4 if current else 2
        draw.rounded_rectangle(
            box,
            radius=10,
            fill="#202823",
            outline=outline,
            width=width,
        )

        avatar = (box[0] + 9, box[1] + 9, box[0] + 59, box[1] + 59)
        draw.ellipse(avatar, fill=accent)
        fallback_name = (
            "Máquina" if player.is_bot else f"Jogador {player.seat_position + 1}"
        )
        name = names.get(player.user_id, fallback_name)
        _draw_centered_text(draw, _initials(name), avatar, _font(17, bold=True), TEXT)

        safe_name = _fit_text(draw, name, _font(17, bold=True), box[2] - box[0] - 82)
        draw.text(
            (box[0] + 70, box[1] + 13),
            safe_name,
            font=_font(17, bold=True),
            fill=TEXT,
        )
        detail = _player_detail(session, player.user_id, player.accepted, current)
        draw.text((box[0] + 70, box[1] + 38), detail, font=_font(14), fill=MUTED)


def _draw_lobby(draw: ImageDraw.ImageDraw, session: TrucoSession) -> None:
    accepted = len(session.accepted_user_ids)
    _draw_center_notice(draw, f"{accepted}/4 confirmados", TEXT)
    subtitle = "A partida começa quando todos aceitarem"
    _draw_centered_at(draw, subtitle, 345, _font(16), MUTED)


def _draw_playing_state(
    draw: ImageDraw.ImageDraw,
    session: TrucoSession,
    names: dict[int, str],
    *,
    reveal_round: bool = False,
) -> None:
    reveal = session.last_round_reveal if reveal_round else None
    hand_number = reveal.hand_number if reveal else session.hand_number
    round_number = reveal.round_number if reveal else session.round_number
    if reveal:
        round_blue = reveal.round_wins_blue
        round_red = reveal.round_wins_red
        phase = f"RODADA {round_number} CONCLUÍDA"
    else:
        round_blue = session.round_winners.count(TrucoTeam.BLUE)
        round_red = session.round_winners.count(TrucoTeam.RED)
        phase = f"RODADA {round_number}"
    label = (
        f"MÃO {hand_number}   {phase}   "
        f"VALE {reveal.hand_value if reveal else session.hand_value}   "
        f"RODADAS {round_blue} - {round_red}"
    )
    _draw_centered_at(draw, label, 188, _font(17, bold=True), MUTED)

    current_cards = {
        played.user_id: played
        for played in (reveal.cards if reveal else session.played_cards)
        if reveal is not None or played.round_number == session.round_number
    }
    card_positions = (
        {0: (449, 407), 1: (449, 213)}
        if len(session.players) == 2
        else {
            0: (449, 407),
            1: (290, 292),
            2: (449, 213),
            3: (608, 292),
        }
    )
    for player in session.players:
        played = current_cards.get(player.user_id)
        if played is not None:
            _draw_played_card(draw, played, card_positions[player.seat_position])

    vira = reveal.vira if reveal else session.vira
    manilha_rank = reveal.manilha_rank if reveal else session.manilha_rank
    if vira is not None:
        _draw_card(draw, vira, (690, 418), compact=True)
        draw.text((689, 505), "VIRA", font=_font(12, bold=True), fill=MUTED)
        manilha = manilha_rank.value if manilha_rank else "-"
        draw.text(
            (677, 521),
            f"MANILHA {manilha}",
            font=_font(13, bold=True),
            fill=GOLD,
        )

    if reveal is not None:
        result = _round_result_label(reveal.winner)
        accent = (
            BLUE
            if reveal.winner is TrucoTeam.BLUE
            else RED if reveal.winner is TrucoTeam.RED else GOLD
        )
        _draw_center_notice(draw, result, accent, y=319)
        winner_name = names.get(reveal.winner_user_id or 0)
        if winner_name:
            _draw_centered_at(
                draw,
                f"Maior carta: {winner_name}",
                370,
                _font(15, bold=True),
                MUTED,
            )
    elif session.pending_challenge is not None:
        proposed = session.pending_challenge.proposed_value
        target = _team_name(session.pending_challenge.target_team)
        _draw_center_notice(draw, f"TRUCO: vale {proposed}?", GOLD, y=339)
        _draw_centered_at(draw, f"Equipe {target} responde", 379, _font(15), MUTED)
    elif session.is_escurona:
        _draw_center_notice(draw, "ESCURONA", GOLD, y=339)
        _draw_centered_at(draw, "Mão de 11", 379, _font(15), MUTED)
    elif not current_cards:
        _draw_center_notice(draw, "Mesa aberta", TEXT, y=319)
        if session.last_round_reveal is not None:
            last_result = _round_result_label(session.last_round_reveal.winner)
            _draw_centered_at(
                draw,
                f"Última rodada: {last_result}",
                370,
                _font(14, bold=True),
                MUTED,
            )
    elif session.last_round_reveal is not None:
        last_result = _round_result_label(session.last_round_reveal.winner)
        _draw_centered_at(
            draw,
            f"Última rodada: {last_result}",
            363,
            _font(14, bold=True),
            MUTED,
        )


def _draw_finished(draw: ImageDraw.ImageDraw, session: TrucoSession) -> None:
    if session.winning_team is None:
        _draw_center_notice(draw, "Partida encerrada", TEXT)
        return
    team = _team_name(session.winning_team)
    accent = BLUE if session.winning_team is TrucoTeam.BLUE else RED
    _draw_center_notice(draw, f"Equipe {team} venceu", accent)
    _draw_centered_at(draw, "Placar final", 345, _font(15), MUTED)


def _draw_played_card(
    draw: ImageDraw.ImageDraw,
    played: TrucoPlayedCard,
    position: tuple[int, int],
) -> None:
    if played.is_closed:
        _draw_closed_card(draw, position)
    else:
        _draw_card(draw, played.card, position)


def _draw_card(
    draw: ImageDraw.ImageDraw,
    card: TrucoCard,
    position: tuple[int, int],
    *,
    compact: bool = False,
) -> None:
    x, y = position
    width = 54 if compact else CARD_WIDTH
    height = 76 if compact else CARD_HEIGHT
    box = (x, y, x + width, y + height)
    draw.rounded_rectangle(box, radius=7, fill=CARD, outline=CARD_LINE, width=2)
    color = CARD_RED if card.suit in {TrucoSuit.OUROS, TrucoSuit.COPAS} else CARD_BLACK
    rank = card.rank_label
    draw.text((x + 8, y + 5), rank, font=_font(19, bold=True), fill=color)
    symbol_font = _font(29 if not compact else 25)
    _draw_centered_text(draw, card.suit_symbol, box, symbol_font, color)


def _draw_closed_card(draw: ImageDraw.ImageDraw, position: tuple[int, int]) -> None:
    x, y = position
    box = (x, y, x + CARD_WIDTH, y + CARD_HEIGHT)
    draw.rounded_rectangle(box, radius=7, fill=CARD, outline=CARD_LINE, width=2)
    inset = (x + 7, y + 7, x + CARD_WIDTH - 7, y + CARD_HEIGHT - 7)
    draw.rounded_rectangle(inset, radius=5, fill=CARD_DARK, outline=SUBTLE, width=2)
    for offset in range(0, CARD_HEIGHT - 24, 12):
        start_y = y + 10 + offset
        end_y = min(y + CARD_HEIGHT - 10, start_y + 34)
        draw.line(
            (x + 10, start_y, x + CARD_WIDTH - 10, end_y),
            fill="#4f6258",
            width=2,
        )


def _draw_center_notice(
    draw: ImageDraw.ImageDraw,
    text: str,
    fill: str,
    *,
    y: int = 305,
) -> None:
    font = _font(24, bold=True)
    width = draw.textlength(text, font=font)
    box = (WIDTH / 2 - width / 2 - 20, y, WIDTH / 2 + width / 2 + 20, y + 44)
    draw.rounded_rectangle(box, radius=8, fill="#13261c", outline="#37634b", width=2)
    _draw_centered_text(draw, text, box, font, fill)


def _draw_team_mark(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    fill: str,
) -> None:
    draw.ellipse((x, y, x + 8, y + 8), fill=fill)
    draw.text((x + 14, y - 4), label, font=_font(12, bold=True), fill=MUTED)


def _draw_right_text(
    draw: ImageDraw.ImageDraw,
    right: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    draw.text((right - draw.textlength(text, font=font), y), text, font=font, fill=fill)


def _draw_centered_at(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    width = draw.textlength(text, font=font)
    draw.text(((WIDTH - width) / 2, y), text, font=font, fill=fill)


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[float, float, float, float],
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = box[0] + (box[2] - box[0] - width) / 2
    y = box[1] + (box[3] - box[1] - height) / 2 - bounds[1]
    draw.text((x, y), text, font=font, fill=fill)


def _player_detail(
    session: TrucoSession,
    user_id: int,
    accepted: bool,
    current: bool,
) -> str:
    if session.status is TrucoGameStatus.LOBBY:
        return "Confirmado" if accepted else "Aguardando aceite"
    if current:
        return "Sua vez" if user_id == session.created_by else "Jogando agora"
    if session.status is TrucoGameStatus.FINISHED:
        player = session.player(user_id)
        if player and player.team is session.winning_team:
            return "Vencedor"
        return "Partida encerrada"
    played = any(
        card.user_id == user_id and card.round_number == session.round_number
        for card in session.played_cards
    )
    return "Carta na mesa" if played else "Aguardando"


def _status_label(session: TrucoSession) -> str:
    if session.status is TrucoGameStatus.LOBBY:
        return "Aguardando confirmações"
    if session.status is TrucoGameStatus.FINISHED:
        return "Partida finalizada"
    if session.status is TrucoGameStatus.CANCELLED:
        return "Partida cancelada"
    return "Partida em andamento"


def _team_name(team: TrucoTeam) -> str:
    return "Azul" if team is TrucoTeam.BLUE else "Vermelha"


def _round_result_label(winner: TrucoTeam | None) -> str:
    if winner is None:
        return "Rodada empatada"
    return f"Equipe {_team_name(winner)} venceu"


def _initials(name: str) -> str:
    parts = [part for part in name.replace("_", " ").split() if part]
    if not parts:
        return "TR"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: float,
) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    shortened = text
    while shortened and draw.textlength(f"{shortened}…", font=font) > max_width:
        shortened = shortened[:-1]
    return f"{shortened}…" if shortened else "…"


@lru_cache(maxsize=32)
def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        "arialbd.ttf" if bold else "arial.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
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
