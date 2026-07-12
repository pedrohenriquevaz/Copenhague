from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.models.uno import UnoCard, UnoColor, UnoGameStatus, UnoSession, UnoValue

UNO_TABLE_FILENAME = "uno_table.png"

WIDTH = 960
HEIGHT = 640
BACKGROUND = "#0d1110"
PANEL = "#171c19"
TABLE = "#1d3d31"
TABLE_LINE = "#3f6554"
TEXT = "#f2f5f3"
MUTED = "#a9b5ae"
SUBTLE = "#68776f"
GOLD = "#d6b867"
CARD_BG = "#f5f1e8"
CARD_DARK = "#242b27"

COLOR_HEX = {
    UnoColor.RED: "#c7544d",
    UnoColor.BLUE: "#4386b8",
    UnoColor.GREEN: "#4a9965",
    UnoColor.YELLOW: "#d3ad43",
}


def render_uno_table_image(
    session: UnoSession,
    *,
    display_names: dict[int, str] | None = None,
) -> bytes:
    """Renderiza somente o estado público da mesa de UNO."""

    names = display_names or {}
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 942, 622), radius=14, fill=PANEL)
    _draw_header(draw, session)
    _draw_table(draw, session, names)
    _draw_players(draw, session, names)
    _draw_footer(draw, session, names)
    output = BytesIO()
    image.save(output, format="PNG", compress_level=6)
    return output.getvalue()


def _draw_header(draw: ImageDraw.ImageDraw, session: UnoSession) -> None:
    title_font = _font(25, bold=True)
    title = _fit_text(draw, session.title.upper(), title_font, 560)
    draw.text((42, 35), title, font=title_font, fill=TEXT)
    draw.text((42, 69), _status_text(session), font=_font(15), fill=MUTED)
    if session.status is UnoGameStatus.PLAYING:
        direction = "HORÁRIO" if session.direction == 1 else "ANTI-HORÁRIO"
        _draw_right_text(draw, 918, 39, direction, _font(15, bold=True), TEXT)
        color = session.current_color
        if color is not None:
            _draw_right_text(
                draw,
                918,
                67,
                f"COR ATUAL  {color.label.upper()}",
                _font(14, bold=True),
                COLOR_HEX[color],
            )


def _draw_table(
    draw: ImageDraw.ImageDraw,
    session: UnoSession,
    names: dict[int, str],
) -> None:
    accent = COLOR_HEX.get(session.current_color, TABLE_LINE)
    draw.ellipse((245, 125, 715, 520), fill="#122a21", outline=accent, width=4)
    draw.ellipse((265, 145, 695, 500), fill=TABLE, outline=TABLE_LINE, width=2)

    if session.status is UnoGameStatus.LOBBY:
        _draw_center_notice(draw, f"{len(session.players)}/10 jogadores", 280)
        _draw_centered_at(draw, "Aguardando o criador iniciar", 334, _font(16), MUTED)
        return
    if session.status is UnoGameStatus.CANCELLED:
        _draw_center_notice(draw, "PARTIDA ENCERRADA", 296)
        return
    if session.status is UnoGameStatus.FINISHED:
        _draw_center_notice(draw, "VITÓRIA", 275, fill=GOLD)
        if session.winner_user_id is not None:
            _draw_centered_at(
                draw,
                names.get(
                    session.winner_user_id,
                    f"Jogador {session.winner_user_id}",
                ),
                334,
                _font(17, bold=True),
                TEXT,
            )
        return

    _draw_deck(draw, len(session.draw_pile), (322, 246))
    if session.top_card is not None:
        _draw_card(draw, session.top_card, (455, 226))
    draw.text((319, 386), "MONTE", font=_font(13, bold=True), fill=MUTED)
    draw.text((449, 386), "DESCARTE", font=_font(13, bold=True), fill=MUTED)
    _draw_direction(draw, session.direction, (610, 292))
    current = session.current_player
    if current is not None:
        _draw_centered_at(
            draw,
            "JOGADOR DA VEZ",
            423,
            _font(12, bold=True),
            MUTED,
        )
        _draw_centered_at(
            draw,
            names.get(current.user_id, f"Jogador {current.user_id}"),
            444,
            _font(17, bold=True),
            TEXT,
        )


def _draw_players(
    draw: ImageDraw.ImageDraw,
    session: UnoSession,
    names: dict[int, str],
) -> None:
    current_id = session.current_player.user_id if session.current_player else None
    for index, player in enumerate(session.players):
        column = 0 if index < 5 else 1
        row = index if column == 0 else index - 5
        x = 30 if column == 0 else 730
        y = 120 + row * 72
        box = (x, y, x + 200, y + 56)
        current = player.user_id == current_id
        accent = GOLD if current else "#39463f"
        draw.rounded_rectangle(box, radius=8, fill="#202723", outline=accent, width=3)
        avatar = (x + 8, y + 8, x + 48, y + 48)
        draw.ellipse(avatar, fill="#3d5147")
        name = names.get(player.user_id, f"Jogador {index + 1}")
        _draw_centered_text(draw, _initials(name), avatar, _font(14, bold=True), TEXT)
        fitted = _fit_text(draw, name, _font(15, bold=True), 128)
        draw.text((x + 58, y + 8), fitted, font=_font(15, bold=True), fill=TEXT)
        count = len(player.hand)
        detail = (
            "Aguardando início"
            if session.status is UnoGameStatus.LOBBY
            else f"{count} carta{'s' if count != 1 else ''}"
        )
        draw.text((x + 58, y + 30), detail, font=_font(13), fill=MUTED)


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    session: UnoSession,
    names: dict[int, str],
) -> None:
    line = session.last_action or "Aguardando uma ação."
    for user_id, name in names.items():
        line = line.replace(f"<@{user_id}>", name)
    draw.line((42, 548, 918, 548), fill="#303a35", width=2)
    draw.text((42, 565), "ÚLTIMA AÇÃO", font=_font(12, bold=True), fill=SUBTLE)
    fitted = _fit_text(draw, line.replace("<", "").replace(">", ""), _font(16), 730)
    draw.text((42, 586), fitted, font=_font(16), fill=TEXT)
    if session.status is UnoGameStatus.PLAYING:
        pile = f"{len(session.draw_pile)} no monte"
        _draw_right_text(draw, 918, 582, pile, _font(15, bold=True), MUTED)


def _draw_direction(
    draw: ImageDraw.ImageDraw,
    direction: int,
    center: tuple[int, int],
) -> None:
    x, y = center
    draw.arc((x - 25, y - 25, x + 25, y + 25), 35, 325, fill=SUBTLE, width=5)
    if direction == 1:
        draw.polygon(
            [(x + 22, y - 17), (x + 31, y - 4), (x + 15, y - 3)],
            fill=SUBTLE,
        )
    else:
        draw.polygon(
            [(x - 22, y - 17), (x - 31, y - 4), (x - 15, y - 3)],
            fill=SUBTLE,
        )


def _draw_card(
    draw: ImageDraw.ImageDraw,
    card: UnoCard,
    position: tuple[int, int],
) -> None:
    x, y = position
    box = (x, y, x + 92, y + 132)
    color = COLOR_HEX.get(card.color, CARD_DARK)
    draw.rounded_rectangle(box, radius=11, fill=CARD_BG, outline="#d8d2c5", width=2)
    inner = (x + 7, y + 7, x + 85, y + 125)
    draw.rounded_rectangle(inner, radius=9, fill=color)
    draw.ellipse((x + 17, y + 25, x + 75, y + 107), fill="#f5f1e8")
    if card.value is UnoValue.WILD:
        _draw_color_ball(draw, (x + 46, y + 66), 25)
    else:
        label = _card_symbol(card.value)
        _draw_centered_text(draw, label, box, _font(28, bold=True), color)


def _draw_color_ball(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
) -> None:
    x, y = center
    draw.pieslice(
        (x - radius, y - radius, x + radius, y + radius),
        180,
        270,
        fill=COLOR_HEX[UnoColor.RED],
    )
    draw.pieslice(
        (x - radius, y - radius, x + radius, y + radius),
        270,
        360,
        fill=COLOR_HEX[UnoColor.BLUE],
    )
    draw.pieslice(
        (x - radius, y - radius, x + radius, y + radius),
        0,
        90,
        fill=COLOR_HEX[UnoColor.GREEN],
    )
    draw.pieslice(
        (x - radius, y - radius, x + radius, y + radius),
        90,
        180,
        fill=COLOR_HEX[UnoColor.YELLOW],
    )
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius), outline=CARD_DARK, width=2
    )


def _draw_deck(
    draw: ImageDraw.ImageDraw,
    count: int,
    position: tuple[int, int],
) -> None:
    x, y = position
    for offset in (8, 4, 0):
        box = (x + offset, y - offset, x + 80 + offset, y + 116 - offset)
        draw.rounded_rectangle(box, radius=10, fill=CARD_BG, outline="#beb8ad")
    inner = (x + 7, y + 7, x + 73, y + 109)
    draw.rounded_rectangle(inner, radius=8, fill="#252c28")
    _draw_centered_text(draw, "UNO", inner, _font(20, bold=True), TEXT)
    badge = (x + 54, y + 88, x + 84, y + 118)
    draw.ellipse(badge, fill=GOLD)
    _draw_centered_text(draw, str(count), badge, _font(12, bold=True), CARD_DARK)


def _draw_center_notice(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    *,
    fill: str = TEXT,
) -> None:
    font = _font(23, bold=True)
    width = draw.textlength(text, font=font)
    box = (480 - width / 2 - 20, y, 480 + width / 2 + 20, y + 46)
    draw.rounded_rectangle(box, radius=8, fill="#14271f", outline=TABLE_LINE)
    _draw_centered_text(draw, text, box, font, fill)


def _card_symbol(value: UnoValue) -> str:
    return {
        UnoValue.SKIP: "Ø",
        UnoValue.REVERSE: "↻",
        UnoValue.DRAW_TWO: "+2",
        UnoValue.WILD: "",
        UnoValue.WILD_DRAW_FOUR: "+4",
    }.get(value, value.value)


def _status_text(session: UnoSession) -> str:
    status = {
        UnoGameStatus.LOBBY: "Lobby aberto",
        UnoGameStatus.PLAYING: "Partida em andamento",
        UnoGameStatus.FINISHED: "Partida finalizada",
        UnoGameStatus.CANCELLED: "Partida cancelada",
    }[session.status]
    return f"{status} · Aposta {session.stake} pontos"


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
    draw.text(
        ((WIDTH - draw.textlength(text, font=font)) / 2, y), text, font=font, fill=fill
    )


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


def _initials(name: str) -> str:
    parts = [part for part in name.replace("_", " ").split() if part]
    if not parts:
        return "UN"
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
