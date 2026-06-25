from __future__ import annotations

from collections.abc import Iterable

import discord

from app.models.bolao import BolaoEvent, BolaoGuess
from app.models.form import FormDefinition, FormQuestionType, FormResponse
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


def build_bolao_event_embed(
    event: BolaoEvent,
    *,
    closed: bool = False,
) -> discord.Embed:
    """Cria o embed publico de um bolao."""

    color = (
        discord.Color.red()
        if closed or not event.is_active
        else discord.Color.blue()
    )
    embed = discord.Embed(
        title=event.title,
        description=event.description,
        color=color,
        timestamp=event.created_at,
    )
    embed.add_field(name="Jogo", value=f"{event.team_1} x {event.team_2}", inline=False)
    embed.add_field(name="Premio", value=event.prize, inline=False)
    embed.add_field(
        name="Como participar",
        value="Clique no botao abaixo e envie seu palpite de placar.",
        inline=False,
    )
    embed.add_field(
        name="Responsavel",
        value=f"<@{event.receiver_user_id}>",
        inline=True,
    )

    if closed or not event.is_active:
        embed.set_footer(text=f"Bolao #{event.id} encerrado")
    else:
        embed.set_footer(text=f"Bolao #{event.id}")
    return embed


def build_bolao_list_embed(events: list[BolaoEvent]) -> discord.Embed:
    """Cria o embed com a lista de boloes ativos."""

    embed = discord.Embed(
        title="Boloes ativos",
        color=discord.Color.blue(),
    )

    if not events:
        embed.description = "Nao ha boloes ativos no momento."
        return embed

    lines = [
        (
            f"**#{event.id}** - {event.title}\n"
            f"{event.team_1} x {event.team_2} | Premio: {event.prize}"
        )
        for event in events
    ]
    embed.description = _format_embed_lines(lines, limit=4000)
    return embed


def format_bolao_guess(event: BolaoEvent, guess: BolaoGuess) -> str:
    """Formata um palpite com os nomes dos times."""

    return (
        f"{event.team_1} {guess.score_team_1} x "
        f"{guess.score_team_2} {event.team_2}"
    )


def build_form_embed(
    form: FormDefinition,
    *,
    closed: bool = False,
) -> discord.Embed:
    """Cria o embed publico de um formulario."""

    embed = discord.Embed(
        title=form.title,
        description=form.description,
        color=(
            discord.Color.red()
            if closed or not form.is_active
            else discord.Color.teal()
        ),
        timestamp=form.created_at,
    )
    embed.add_field(
        name="Como responder",
        value="Clique no botao abaixo para preencher o formulario.",
        inline=False,
    )
    embed.add_field(
        name="Perguntas",
        value=_format_embed_lines(
            [
                (
                    f"{index}. {question.label} "
                    f"({_format_form_question_type(question.type)})"
                )
                for index, question in enumerate(form.questions, start=1)
            ],
            limit=1024,
        ),
        inline=False,
    )
    embed.add_field(
        name="Respostas",
        value=f"<#{form.response_channel_id}>",
        inline=True,
    )
    embed.set_footer(
        text=(
            f"Formulario #{form.id} encerrado"
            if closed or not form.is_active
            else f"Formulario #{form.id}"
        )
    )
    return embed


def build_form_list_embed(forms: list[FormDefinition]) -> discord.Embed:
    """Cria o embed com formularios ativos."""

    embed = discord.Embed(
        title="Formularios ativos",
        color=discord.Color.teal(),
    )

    if not forms:
        embed.description = "Nao ha formularios ativos no momento."
        return embed

    embed.description = _format_embed_lines(
        [
            (
                f"**#{form.id}** - {form.title}\n"
                f"Respostas: <#{form.response_channel_id}> | "
                f"Perguntas: {len(form.questions)}"
            )
            for form in forms
        ],
        limit=4000,
    )
    return embed


def build_form_response_embed(
    form: FormDefinition,
    response: FormResponse,
) -> discord.Embed:
    """Cria o embed enviado ao canal de respostas."""

    embed = discord.Embed(
        title=f"Resposta: {form.title}",
        color=discord.Color.teal(),
        timestamp=response.created_at,
    )
    embed.set_footer(text=f"Formulario #{form.id} | Resposta #{response.id}")

    for question in form.questions:
        answer = response.answers.get(question.id, "-") or "-"
        embed.add_field(
            name=question.label[:256],
            value=answer[:1024],
            inline=False,
        )

    return embed


def _format_form_question_type(question_type: FormQuestionType) -> str:
    if question_type is FormQuestionType.SHORT:
        return "resposta curta"
    if question_type is FormQuestionType.MULTI_SELECT:
        return "multipla escolha"
    return "combo-box"


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
    winner_lines: Iterable[str] | None = None,
) -> discord.Embed:
    """Cria o embed de encerramento com premios pendentes e ganhadores."""

    embed = discord.Embed(
        title=f"Evento encerrado: {event.title}",
        description="O evento foi finalizado.",
        color=discord.Color.red(),
    )

    remaining_list = list(remaining_codes)
    if not remaining_list:
        embed.add_field(
            name="Codigos premiados nao resgatados",
            value="Nenhum codigo premiado ficou sem resgate.",
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
            name=f"Codigos premiados nao resgatados ({len(remaining_list)})",
            value=_format_embed_lines(lines),
            inline=False,
        )

    winners = list(winner_lines or [])
    if not winners:
        embed.add_field(
            name="Ganhadores",
            value="Nenhum codigo premiado foi resgatado.",
            inline=False,
        )
    else:
        embed.add_field(
            name=f"Ganhadores ({len(winners)})",
            value=_format_embed_lines(winners),
            inline=False,
        )

    embed.set_footer(text=f"Evento #{event.id} encerrado")
    return embed


def _format_embed_lines(lines: list[str], *, limit: int = 1024) -> str:
    value = ""
    shown = 0

    for line in lines:
        suffix = f"\n... e mais {len(lines) - shown}" if shown < len(lines) else ""
        candidate = f"{value}\n{line}" if value else line
        if len(candidate) + len(suffix) > limit:
            break

        value = candidate
        shown += 1

    if shown < len(lines):
        remaining = len(lines) - shown
        ellipsis = f"... e mais {remaining}"
        value = f"{value}\n{ellipsis}" if value else ellipsis

    return value or "-"
