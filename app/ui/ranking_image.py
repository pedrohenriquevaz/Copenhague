from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.models.economy import UserWallet
from app.models.guild_settings import GuildEconomySettings
from app.utils.embeds import format_points

RANKING_IMAGE_FILENAME = "ranking.png"
RANKING_PODIUM_FILENAME = RANKING_IMAGE_FILENAME

WIDTH = 900
HEIGHT = 1280

DARK_BLUE = "#082142"
DEEP_BLUE = "#061326"
CYAN = "#43c8ff"
ORANGE = "#ff8a22"
TEXT = "#f7fbff"
MUTED = "#b9d3ee"
LINE = "#d7ecff"
GOLD = "#f2be42"
SILVER = "#c8d4e5"
BRONZE = "#d28b52"
GREEN = "#66e0a3"
ROW_FILL = "#4f7890"
ROW_FILL_ALT = "#6d8792"
ROW_OUTLINE = "#d7ecff"


def render_ranking_podium_image(
    wallets: list[UserWallet],
    settings: GuildEconomySettings,
    *,
    display_names: dict[int, str] | None = None,
    avatar_images: dict[int, bytes] | None = None,
) -> bytes:
    """Renderiza o ranking completo como uma única imagem."""

    display_names = display_names or {}
    avatar_images = avatar_images or {}

    image = Image.new("RGB", (WIDTH, HEIGHT), DEEP_BLUE)
    draw = ImageDraw.Draw(image)
    _draw_background(image)
    _draw_title(draw, settings)
    _draw_top_three(draw, image, wallets[:3], settings, display_names, avatar_images)
    _draw_classification_label(draw)
    _draw_ranking_rows(
        draw,
        image,
        wallets[3:10],
        settings,
        display_names,
        avatar_images,
    )

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _draw_background(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        if y < 580:
            ratio = y / 580
            color = _blend(_hex(DEEP_BLUE), _hex(DARK_BLUE), ratio)
        else:
            ratio = (y - 580) / (HEIGHT - 580)
            color = _blend(_hex(DARK_BLUE), _hex(ORANGE), ratio)
        draw.line((0, y, WIDTH, y), fill=color)


def _draw_title(
    draw: ImageDraw.ImageDraw,
    settings: GuildEconomySettings,
) -> None:
    title = "Ranking de Pontos"
    subtitle = f"Top 10 por saldo atual em {settings.currency_name}"
    title_font = _font(42, bold=True)
    subtitle_font = _font(22, bold=True)
    title_width = draw.textlength(title, font=title_font)
    subtitle_width = draw.textlength(subtitle, font=subtitle_font)
    draw.text(((WIDTH - title_width) / 2, 50), title, font=title_font, fill=TEXT)
    draw.text(
        ((WIDTH - subtitle_width) / 2, 104),
        subtitle,
        font=subtitle_font,
        fill=MUTED,
    )
    draw.rounded_rectangle((330, 150, 570, 156), radius=3, fill=CYAN)


def _draw_top_three(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    wallets: list[UserWallet],
    settings: GuildEconomySettings,
    display_names: dict[int, str],
    avatar_images: dict[int, bytes],
) -> None:
    positions = [
        (1, 348, 210, 180, GOLD),
        (2, 92, 270, 150, SILVER),
        (3, 652, 290, 140, BRONZE),
    ]
    by_rank = {index: wallet for index, wallet in enumerate(wallets, start=1)}
    for rank, x, y, size, color in positions:
        wallet = by_rank.get(rank)
        if wallet is None:
            continue
        _draw_top_member(
            draw,
            image,
            wallet,
            settings,
            x=x,
            y=y,
            avatar_size=size,
            rank=rank,
            accent=color,
            display_name=display_names.get(wallet.user_id),
            avatar_bytes=avatar_images.get(wallet.user_id),
        )


def _draw_top_member(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    wallet: UserWallet,
    settings: GuildEconomySettings,
    *,
    x: int,
    y: int,
    avatar_size: int,
    rank: int,
    accent: str,
    display_name: str | None,
    avatar_bytes: bytes | None,
) -> None:
    name = display_name or f"Usuário {wallet.user_id}"
    center_x = x + avatar_size // 2

    crown_y = y - 54
    _draw_rank_crown(draw, (center_x, crown_y), rank, accent)
    draw.rounded_rectangle(
        (x - 8, y - 8, x + avatar_size + 8, y + avatar_size + 8),
        radius=18,
        outline=accent,
        width=7,
    )
    avatar = _avatar_image(avatar_bytes, name, avatar_size, rounded=True)
    image.paste(avatar, (x, y), avatar)

    name_font = _font(22, bold=True)
    score_font = _font(18, bold=True)
    name_text = _fit_text(draw, name, name_font, avatar_size + 60)
    score_text = _short_points(wallet.balance, settings.currency_name)
    name_width = draw.textlength(name_text, font=name_font)
    score_width = draw.textlength(score_text, font=score_font)
    draw.text(
        (center_x - name_width / 2, y + avatar_size + 14),
        name_text,
        font=name_font,
        fill=TEXT,
    )
    draw.text(
        (center_x - score_width / 2, y + avatar_size + 42),
        score_text,
        font=score_font,
        fill=MUTED,
    )


def _draw_rank_crown(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    rank: int,
    accent: str,
) -> None:
    x, y = center
    draw.line((x, y + 30, x, y + 8), fill=accent, width=5)
    draw.line((x - 26, y + 30, x - 26, y + 18), fill=accent, width=5)
    draw.line((x + 26, y + 30, x + 26, y + 18), fill=accent, width=5)
    draw.line((x - 26, y + 30, x + 26, y + 30), fill=accent, width=5)
    draw.ellipse((x - 8, y, x + 8, y + 16), outline=accent, width=4)
    draw.ellipse((x - 34, y + 10, x - 18, y + 26), outline=accent, width=4)
    draw.ellipse((x + 18, y + 10, x + 34, y + 26), outline=accent, width=4)

    badge = (x + 34, y + 36, x + 84, y + 86)
    draw.ellipse(badge, fill=accent)
    _draw_centered_text(draw, f"{rank}º", badge, _font(18, bold=True), DEEP_BLUE)


def _draw_classification_label(draw: ImageDraw.ImageDraw) -> None:
    y = 535
    draw.line((72, y, 296, y), fill=LINE, width=3)
    draw.line((604, y, 828, y), fill=LINE, width=3)
    draw.polygon([(62, y), (72, y - 8), (82, y), (72, y + 8)], fill=LINE)
    draw.polygon([(818, y), (828, y - 8), (838, y), (828, y + 8)], fill=LINE)
    label = "4-10"
    font = _font(27, bold=True)
    width = draw.textlength(label, font=font)
    draw.text(((WIDTH - width) / 2, y - 18), label, font=font, fill=TEXT)


def _draw_ranking_rows(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    wallets: list[UserWallet],
    settings: GuildEconomySettings,
    display_names: dict[int, str],
    avatar_images: dict[int, bytes],
) -> None:
    start_y = 580
    row_height = 64
    gap = 14
    for offset, wallet in enumerate(wallets):
        rank = offset + 4
        y = start_y + offset * (row_height + gap)
        _draw_ranking_row(
            draw,
            image,
            wallet,
            settings,
            rank=rank,
            y=y,
            row_height=row_height,
            fill=ROW_FILL if offset % 2 == 0 else ROW_FILL_ALT,
            display_name=display_names.get(wallet.user_id),
            avatar_bytes=avatar_images.get(wallet.user_id),
        )


def _draw_ranking_row(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    wallet: UserWallet,
    settings: GuildEconomySettings,
    *,
    rank: int,
    y: int,
    row_height: int,
    fill: str,
    display_name: str | None,
    avatar_bytes: bytes | None,
) -> None:
    x = 70
    width = WIDTH - 140
    draw.rounded_rectangle(
        (x, y, x + width, y + row_height),
        radius=2,
        fill=fill,
        outline=ROW_OUTLINE,
        width=2,
    )
    draw.text((x + 18, y + 16), str(rank), font=_font(25, bold=True), fill=TEXT)

    name = display_name or f"Usuário {wallet.user_id}"
    avatar = _avatar_image(avatar_bytes, name, 48, rounded=False)
    image.paste(avatar, (x + 70, y + 8), avatar)

    name_font = _font(20, bold=True)
    name_text = _fit_text(draw, name, name_font, 360)
    draw.text((x + 136, y + 19), name_text, font=name_font, fill=TEXT)

    points_text = _short_points(wallet.balance, settings.currency_name)
    points_font = _font(15, bold=True)
    text_width = draw.textlength(points_text, font=points_font)
    pill = (x + width - 214, y + 18, x + width - 52, y + 46)
    draw.rounded_rectangle(pill, radius=4, fill="#7e9cae")
    draw.text(
        (pill[0] + (pill[2] - pill[0] - text_width) / 2, y + 24),
        points_text,
        font=points_font,
        fill=TEXT,
    )


def _avatar_image(
    avatar_bytes: bytes | None,
    fallback_name: str,
    size: int,
    *,
    rounded: bool,
) -> Image.Image:
    if avatar_bytes:
        try:
            avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            avatar = _center_crop(avatar).resize((size, size), Image.Resampling.LANCZOS)
        except OSError:
            avatar = _fallback_avatar(fallback_name, size)
    else:
        avatar = _fallback_avatar(fallback_name, size)

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    if rounded:
        mask_draw.ellipse((0, 0, size, size), fill=255)
    else:
        mask_draw.rounded_rectangle((0, 0, size, size), radius=5, fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(avatar, (0, 0), mask)
    return output


def _fallback_avatar(name: str, size: int) -> Image.Image:
    colors = ["#5865f2", "#0ea5e9", "#10b981", "#f97316", "#ef4444", "#8b5cf6"]
    color = colors[sum(ord(char) for char in name) % len(colors)]
    avatar = Image.new("RGBA", (size, size), color)
    draw = ImageDraw.Draw(avatar)
    initials = _initials(name)
    _draw_centered_text(
        draw,
        initials,
        (0, 0, size, size),
        _font(max(18, size // 3), bold=True),
        TEXT,
    )
    return avatar


def _center_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


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


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    clipped = text
    while clipped and draw.textlength(f"{clipped}...", font=font) > max_width:
        clipped = clipped[:-1]
    return f"{clipped}..." if clipped else "..."


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _short_points(amount: int, currency_name: str) -> str:
    return format_points(amount, currency_name)


def _initials(name: str) -> str:
    parts = [part for part in name.replace("_", " ").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def _hex(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _blend(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    ratio = max(0, min(1, ratio))
    return (
        round(start[0] + (end[0] - start[0]) * ratio),
        round(start[1] + (end[1] - start[1]) * ratio),
        round(start[2] + (end[2] - start[2]) * ratio),
    )
