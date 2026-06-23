from __future__ import annotations

from collections.abc import Iterable

import discord

from app.models.giveaway import GiveawayCode, GiveawayEvent, GiveawayEventStats


def format_reward_text(
    reward_name: str | None,
    reward_amount: int | None,
) -> str:
    """Formata a representacao textual de uma premiacao."""

    if reward_name and reward_amount is not None:
        return f"{reward_amount} {reward_name}"

    if reward_name:
        return reward_name

    if reward_amount is not None:
        return str(reward_amount)

    return "sem premio"


def hex_code_to_color(code: str) -> discord.Color:
    """Converte um HEX de 6 caracteres em cor do Discord."""

    normalized = code.strip().removeprefix("#")
    try:
        return discord.Color(int(normalized, 16))
    except ValueError:
        return discord.Color.gold()


def parse_color_value(value: str | None) -> int | None:
    """Converte um valor textual hexadecimal em inteiro de cor."""

    if value is None or not value.strip():
        return None

    normalized = value.strip().removeprefix("#")
    parsed = int(normalized, 16)
    if parsed < 0 or parsed > 0xFFFFFF:
        raise ValueError("A cor precisa estar entre 000000 e FFFFFF.")
    return parsed


def build_giveaway_event_embed(
    event: GiveawayEvent,
    stats: GiveawayEventStats | None,
    *,
    closed: bool = False,
) -> discord.Embed:
    """Cria o embed publicado no canal do evento."""

    embed = discord.Embed(
        title=event.title,
        description=event.description,
        color=(
            discord.Color(event.embed_color)
            if event.embed_color is not None
            else discord.Color.gold()
        ),
        timestamp=event.created_at,
    )

    embed.add_field(
        name="Como participar",
        value=(
            "Clique no botao abaixo para receber um codigo.\n"
            "Cada usuario pode participar apenas uma vez por evento."
        ),
        inline=False,
    )

    embed.add_field(
        name="Sobre os codigos",
        value=(
            "Alguns codigos possuem premio e outros nao. "
            "O resgate e feito de forma aleatoria entre os codigos restantes."
        ),
        inline=False,
    )

    if event.expires_at is not None:
        embed.add_field(
            name="Encerra em",
            value=f"<t:{int(event.expires_at.timestamp())}:F>",
            inline=False,
        )

    if stats is not None:
        embed.add_field(
            name="Codigos totais",
            value=str(stats.total_codes),
            inline=True,
        )
        embed.add_field(
            name="Com premio",
            value=str(stats.rewarded_codes),
            inline=True,
        )
        embed.add_field(
            name="Disponiveis",
            value=str(stats.available_codes),
            inline=True,
        )

    if closed:
        embed.set_footer(text=f"Evento #{event.id} encerrado")
    else:
        embed.set_footer(text=f"Evento #{event.id}")
    return embed


def build_giveaway_claim_embed(
    code: str,
    *,
    reward_name: str | None,
    reward_amount: int | None,
    won: bool,
) -> discord.Embed:
    """Cria o embed de resposta do resgate do usuario."""

    color = hex_code_to_color(code)
    embed = discord.Embed(
        title="Codigo resgatado",
        color=color,
    )
    embed.add_field(name="Codigo", value=f"`{code}`", inline=False)

    if won:
        embed.description = "Parabens, esse codigo veio premiado."
        embed.add_field(
            name="Premiacao",
            value=format_reward_text(reward_name, reward_amount),
            inline=False,
        )
    else:
        embed.description = "Dessa vez o codigo nao veio premiado."

    return embed


def build_giveaway_final_embed(
    event: GiveawayEvent,
    remaining_codes: Iterable[GiveawayCode],
) -> discord.Embed:
    """Cria o embed de encerramento com os codigos restantes."""

    embed = discord.Embed(
        title=f"Evento encerrado: {event.title}",
        description="O evento foi finalizado e os codigos restantes estao abaixo.",
        color=discord.Color.red(),
    )

    remaining_list = list(remaining_codes)
    if not remaining_list:
        embed.add_field(
            name="Codigos restantes",
            value="Nenhum codigo restou ao final do evento.",
            inline=False,
        )
    else:
        lines = [
            (
                f"`{item.code}` - "
                f"{format_reward_text(item.reward_name, item.reward_amount)}"
            )
            for item in remaining_list
        ]
        embed.add_field(
            name=f"Codigos restantes ({len(remaining_list)})",
            value="\n".join(lines[:25]) + ("\n..." if len(lines) > 25 else ""),
            inline=False,
        )

    return embed
