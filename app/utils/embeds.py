from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import discord

from app.models.bolao import BolaoEvent, BolaoGuess
from app.models.economy import (
    ActivityConversionResult,
    CreditProtectionState,
    EconomyTransaction,
    SavingsOverview,
    UserWallet,
)
from app.models.form import FormDefinition, FormQuestionType, FormResponse
from app.models.game_progress import UserGameAchievement
from app.models.giveaway import GiveawayCode, GiveawayEvent, GiveawayEventStats
from app.models.guild_settings import GuildEconomySettings
from app.models.shop import (
    LevelConfig,
    LevelUpgradePurchase,
    RewardItem,
    RewardPurchase,
    RewardType,
)


@dataclass(frozen=True, slots=True)
class ProfileBadge:
    """Pin exibido no perfil público de economia."""

    emoji: str
    name: str
    description: str


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


def format_points(amount: int, currency_name: str = "pontos") -> str:
    """Formata pontos com separador visual simples."""

    return f"{amount:,}".replace(",", ".") + f" {currency_name}"


def format_percent_bps(value: int) -> str:
    """Formata basis points como percentual em pt-BR."""

    percent = value / 100
    formatted = f"{percent:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{formatted}%"


def build_wallet_embed(
    wallet: UserWallet,
    settings: GuildEconomySettings,
    *,
    title: str = "Carteira",
) -> discord.Embed:
    """Cria embed de saldo."""

    embed = discord.Embed(title=title, color=discord.Color.green())
    embed.add_field(
        name="Saldo atual",
        value=format_points(wallet.balance, settings.currency_name),
        inline=False,
    )
    embed.add_field(
        name="Total ganho",
        value=format_points(wallet.total_earned, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Total gasto",
        value=format_points(wallet.total_spent, settings.currency_name),
        inline=True,
    )
    embed.set_footer(text=f"Guild {wallet.guild_id} | Usuario {wallet.user_id}")
    return embed


def build_profile_badges(
    wallet: UserWallet,
    *,
    top_wallets: list[UserWallet],
    achievements: list[UserGameAchievement],
    level_upgrades: list[LevelUpgradePurchase],
    credit_state: CreditProtectionState | None = None,
    savings_overview: SavingsOverview | None = None,
    owned_levels: list[LevelConfig] | None = None,
) -> list[ProfileBadge]:
    """Monta os pins sociais do perfil a partir dos dados já existentes."""

    badges: list[ProfileBadge] = []
    ranking_position = _ranking_position(wallet.user_id, top_wallets)
    achievement_keys = {item.achievement.achievement_key for item in achievements}

    if ranking_position == 1 and wallet.balance > 0:
        badges.append(ProfileBadge("💰", "Magnata", "Usuário mais rico do servidor."))
    elif ranking_position in {2, 3}:
        badges.append(
            ProfileBadge(
                _ranking_medal(ranking_position),
                f"Top {ranking_position}",
                "Entre os três maiores saldos do servidor.",
            )
        )

    highest_level = max((level.level for level in owned_levels or []), default=0)
    if highest_level:
        badges.append(
            ProfileBadge("🔰", f"Nível {highest_level}", "Upgrade de nível ativo.")
        )
    elif level_upgrades:
        highest_purchase = max(purchase.level for purchase in level_upgrades)
        badges.append(
            ProfileBadge(
                "🔰",
                f"Nível {highest_purchase}",
                "Upgrade de nível adquirido.",
            )
        )

    if "duel_king" in achievement_keys:
        badges.append(ProfileBadge("👑", "Rei do X1", "Venceu 10 duelos."))
    if "blackjack_streak_3" in achievement_keys:
        badges.append(
            ProfileBadge("🔥", "Mesa quente", "Três vitórias seguidas no BlackJack.")
        )
    if len(achievements) >= 10:
        badges.append(
            ProfileBadge(
                "🏅",
                "Colecionador",
                f"{len(achievements)} conquistas desbloqueadas.",
            )
        )

    if wallet.total_earned >= 50_000:
        badges.append(
            ProfileBadge("💼", "Carteira pesada", "Mais de 50.000 pontos ganhos.")
        )
    elif wallet.total_earned >= 10_000:
        badges.append(
            ProfileBadge("💵", "Primeiros 10 mil", "Mais de 10.000 pontos ganhos.")
        )

    if credit_state is not None and credit_state.saves > 0:
        badges.append(
            ProfileBadge(
                "🛡️",
                "Protegido",
                f"{credit_state.saves} save(s) de crédito disponível(is).",
            )
        )
    if savings_overview is not None and savings_overview.account.balance > 0:
        badges.append(
            ProfileBadge("🏦", "Poupador", "Possui saldo guardado na poupança.")
        )

    return badges[:8]


def build_profile_embed(
    wallet: UserWallet,
    settings: GuildEconomySettings,
    *,
    display_name: str,
    avatar_url: str | None = None,
    badges: list[ProfileBadge] | None = None,
    achievements: list[UserGameAchievement] | None = None,
    level_upgrades: list[LevelUpgradePurchase] | None = None,
    owned_levels: list[LevelConfig] | None = None,
    recent_transactions: list[EconomyTransaction] | None = None,
    ranking_position: int | None = None,
    credit_state: CreditProtectionState | None = None,
    savings_overview: SavingsOverview | None = None,
) -> discord.Embed:
    """Cria o perfil econômico completo de um membro."""

    embed = discord.Embed(
        title=f"Perfil de {display_name}",
        color=discord.Color.green(),
    )
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)

    embed.add_field(
        name="Saldo atual",
        value=format_points(wallet.balance, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Total ganho",
        value=format_points(wallet.total_earned, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Total gasto",
        value=format_points(wallet.total_spent, settings.currency_name),
        inline=True,
    )

    ranking_text = f"#{ranking_position}" if ranking_position else "Fora do top 10"
    embed.add_field(name="Ranking", value=ranking_text, inline=True)

    if credit_state is not None:
        protection_text = (
            f"Saves: {credit_state.saves}\n"
            f"Derrotas seguidas: {credit_state.lose_streak}"
        )
        embed.add_field(name="Proteção", value=protection_text, inline=True)

    if savings_overview is not None:
        savings_balance = savings_overview.account.balance
        embed.add_field(
            name="Poupança",
            value=format_points(savings_balance, settings.currency_name),
            inline=True,
        )

    embed.add_field(
        name="Pins e tags",
        value=_format_profile_badges(badges or []),
        inline=False,
    )
    embed.add_field(
        name="Níveis",
        value=_format_profile_levels(owned_levels or [], level_upgrades or []),
        inline=False,
    )
    embed.add_field(
        name="Conquistas em destaque",
        value=_format_profile_achievements(achievements or []),
        inline=False,
    )
    embed.add_field(
        name="Transações recentes",
        value=_format_profile_transactions(
            recent_transactions or [],
            settings,
        ),
        inline=False,
    )
    embed.set_footer(text=f"Usuário {wallet.user_id}")
    return embed


def build_transaction_history_embed(
    transactions: list[EconomyTransaction],
    settings: GuildEconomySettings,
) -> discord.Embed:
    """Cria embed com historico recente."""

    embed = discord.Embed(title="Historico de pontos", color=discord.Color.green())
    if not transactions:
        embed.description = "Nenhuma transacao registrada ainda."
        return embed

    lines = []
    for transaction in transactions:
        sign = "+" if transaction.amount > 0 else ""
        lines.append(
            f"`{sign}{transaction.amount}` {settings.currency_name} | "
            f"{transaction.type.value} | {transaction.reason or 'sem motivo'}"
        )
    embed.description = _format_embed_lines(lines, limit=4000)
    return embed


def build_ranking_embed(
    wallets: list[UserWallet],
    settings: GuildEconomySettings,
    *,
    display_names: dict[int, str] | None = None,
    image_url: str | None = None,
) -> discord.Embed:
    """Cria embed de ranking de saldo."""

    embed = discord.Embed(title="Ranking de pontos", color=discord.Color.green())
    if not wallets:
        embed.description = "Ainda não há carteiras com pontos."
        return embed
    if image_url:
        embed.set_image(url=image_url)

    display_names = display_names or {}
    top_lines = []
    rest_lines = []
    for index, wallet in enumerate(wallets, start=1):
        name = display_names.get(wallet.user_id, f"<@{wallet.user_id}>")
        formatted_balance = format_points(wallet.balance, settings.currency_name)
        if index <= 3:
            top_lines.append(
                f"{_ranking_medal(index)} **{name}** — `{formatted_balance}`"
            )
        else:
            rest_lines.append(f"**#{index}** {name} — `{formatted_balance}`")

    sections = ["**Top 3**\n" + "\n".join(top_lines)]
    if rest_lines:
        sections.append(
            "**Demais posições**\n" + _format_embed_lines(rest_lines, limit=2500)
        )
    embed.description = "\n\n".join(sections)
    return embed


def build_activity_conversion_embed(
    result: ActivityConversionResult,
    settings: GuildEconomySettings,
) -> discord.Embed:
    """Cria embed de resumo de conversao."""

    embed = discord.Embed(title="Atividade convertida", color=discord.Color.green())
    if result.total_points <= 0:
        embed.description = (
            "Voce ainda nao possui atividade nova suficiente para converter."
        )
        embed.add_field(
            name="Minimos atuais",
            value=(
                f"Voz: {settings.min_voice_seconds_to_claim}s | "
                f"Mensagens: {settings.min_messages_to_claim}"
            ),
            inline=False,
        )
        return embed

    embed.add_field(
        name="Tempo novo em call",
        value=f"{result.voice_seconds_delta // 60} minuto(s)",
        inline=True,
    )
    embed.add_field(
        name="Mensagens novas",
        value=str(result.messages_delta),
        inline=True,
    )
    voice_points = format_points(result.voice_points, settings.currency_name)
    message_points = format_points(result.message_points, settings.currency_name)
    total_points = format_points(result.total_points, settings.currency_name)
    points_summary = (
        f"Call: {voice_points}\n"
        f"Mensagens: {message_points}\n"
        f"Total: {total_points}"
    )
    embed.add_field(
        name="Pontos recebidos",
        value=points_summary,
        inline=False,
    )
    embed.add_field(
        name="Saldo atual",
        value=format_points(result.wallet.balance, settings.currency_name),
        inline=False,
    )
    return embed


def build_savings_embed(
    overview: SavingsOverview,
    settings: GuildEconomySettings,
    *,
    title: str = "Poupança",
    description: str | None = None,
) -> discord.Embed:
    """Cria embed da poupanca do jogador."""

    account = overview.account
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green(),
    )
    embed.add_field(
        name="Saldo em caixa",
        value=format_points(overview.wallet.balance, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Saldo na poupança",
        value=format_points(account.balance, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Juros",
        value=f"{format_percent_bps(overview.daily_interest_bps)} ao dia",
        inline=True,
    )
    embed.add_field(
        name="Depósito máximo agora",
        value=format_points(overview.max_deposit, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Juros acumulados",
        value=format_points(account.total_interest_earned, settings.currency_name),
        inline=True,
    )
    if overview.interest_applied > 0:
        embed.add_field(
            name="Juros aplicados agora",
            value=format_points(overview.interest_applied, settings.currency_name),
            inline=True,
        )
    if account.locked_until is not None:
        timestamp = int(account.locked_until.timestamp())
        embed.add_field(
            name="Saque bloqueado até",
            value=f"<t:{timestamp}:F>",
            inline=False,
        )
    else:
        embed.add_field(name="Saque", value="Disponível", inline=False)
    return embed


def build_economy_panel_embed(
    settings: GuildEconomySettings,
    *,
    image_url: str | None = None,
) -> discord.Embed:
    """Cria a embed principal do painel de economia."""

    embed = discord.Embed(
        title="Economia da Comunidade",
        description=(
            "Acumule atividade participando das calls e conversando nos chats.\n"
            "Quando quiser, use os botões abaixo para converter atividade, "
            "consultar saldo, transferir pontos, usar a poupança ou ver histórico."
        ),
        color=discord.Color.green(),
    )
    if image_url:
        embed.set_image(url=image_url)
    embed.add_field(
        name="Conversão atual",
        value=(
            f"1 minuto em call = {settings.voice_points_per_minute} "
            f"{settings.currency_name}\n"
            f"1 mensagem = {settings.message_points} {settings.currency_name}"
        ),
        inline=False,
    )
    return embed


def build_shop_embed(
    rewards: list[RewardItem],
    settings: GuildEconomySettings,
    *,
    image_url: str | None = None,
    intro_text: str | None = None,
    levels: list[LevelConfig] | None = None,
    show_reward_ids: bool = False,
) -> discord.Embed:
    """Cria embed de loja."""

    embed = discord.Embed(title="Loja de recompensas", color=discord.Color.purple())
    if image_url:
        embed.set_image(url=image_url)

    intro = intro_text or (
        "Escolha uma recompensa no menu abaixo para ver os detalhes e confirmar "
        "a compra. Use o botão Consultar Pontos para conferir seu saldo atual."
    )
    level_lines = []
    for level in levels or []:
        saves = f" · {level.saves_reward} save(s)" if level.saves_reward > 0 else ""
        level_lines.append(
            f"🔰 **Nível {level.level}** · <@&{level.role_id}> · "
            f"{format_points(level.price, settings.currency_name)}{saves}"
        )

    if not rewards and not level_lines:
        embed.description = (
            f"{intro}\n\nA loja ainda não possui recompensas disponíveis."
        )
        return embed

    lines = []
    for reward in rewards:
        item_name = f"#{reward.id} · {reward.name}" if show_reward_ids else reward.name
        details = " · ".join(
            [
                format_points(reward.price, settings.currency_name),
                _format_reward_stock_short(reward),
                _format_reward_duration(reward.duration_days),
            ]
        )
        lines.append(f"{_reward_icon(reward)} **{item_name}** — {details}")
    sections = []
    if lines:
        reward_lines = _format_embed_lines(lines, limit=2600, separator="\n\n")
        sections.append(f"**Recompensas**\n{reward_lines}")
    if level_lines:
        formatted_levels = _format_embed_lines(
            level_lines,
            limit=1200,
            separator="\n\n",
        )
        sections.append(f"**Upgrades de nível**\n{formatted_levels}")
    embed.description = f"{intro}\n\n" + "\n\n".join(sections)
    return embed


def build_purchases_embed(
    purchases: list[RewardPurchase],
    settings: GuildEconomySettings,
) -> discord.Embed:
    """Cria embed de compras recentes."""

    embed = discord.Embed(title="Minhas compras", color=discord.Color.purple())
    if not purchases:
        embed.description = "Voce ainda nao comprou recompensas."
        return embed

    lines = [
        (
            f"Compra #{purchase.id} | Recompensa #{purchase.reward_id} | "
            f"{format_points(purchase.price_paid, settings.currency_name)} | "
            f"{purchase.delivery_status.value}"
        )
        for purchase in purchases
    ]
    embed.description = _format_embed_lines(lines, limit=4000)
    return embed


def build_bolao_event_embed(
    event: BolaoEvent,
    *,
    closed: bool = False,
) -> discord.Embed:
    """Cria o embed publico de um bolao."""

    color = (
        discord.Color.red() if closed or not event.is_active else discord.Color.blue()
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
        f"{event.team_1} {guess.score_team_1} x " f"{guess.score_team_2} {event.team_2}"
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


def _format_profile_badges(badges: list[ProfileBadge]) -> str:
    if not badges:
        return "Nenhum pin ativo ainda."
    lines = [
        f"{badge.emoji} **{badge.name}** — {badge.description}" for badge in badges
    ]
    return _format_embed_lines(lines, limit=1000)


def _format_profile_levels(
    owned_levels: list[LevelConfig],
    level_upgrades: list[LevelUpgradePurchase],
) -> str:
    if owned_levels:
        lines = [
            f"🔰 **Nível {level.level}** — <@&{level.role_id}>"
            for level in sorted(owned_levels, key=lambda item: item.level)
        ]
        return _format_embed_lines(lines, limit=1000)

    if level_upgrades:
        lines = [
            f"🔰 **Nível {purchase.level}** — <@&{purchase.role_id}>"
            for purchase in level_upgrades
        ]
        return _format_embed_lines(lines, limit=1000)

    return "Nenhum nível adquirido."


def _format_profile_achievements(
    achievements: list[UserGameAchievement],
) -> str:
    if not achievements:
        return "Nenhuma conquista desbloqueada ainda."

    highlighted = sorted(
        achievements,
        key=lambda item: item.unlocked_at,
        reverse=True,
    )[:6]
    lines = [
        (f"{item.achievement.badge_emoji or '🏷️'} " f"**{item.achievement.name}**")
        for item in highlighted
    ]
    remaining = len(achievements) - len(highlighted)
    if remaining > 0:
        lines.append(f"... e mais {remaining} conquista(s).")
    return _format_embed_lines(lines, limit=1000)


def _format_profile_transactions(
    transactions: list[EconomyTransaction],
    settings: GuildEconomySettings,
) -> str:
    if not transactions:
        return "Nenhuma transação registrada."

    lines = []
    for transaction in transactions:
        sign = "+" if transaction.amount > 0 else ""
        amount = f"{sign}{format_points(transaction.amount, settings.currency_name)}"
        lines.append(f"`{amount}` — {transaction.type.value}")
    return _format_embed_lines(lines, limit=1000)


def _ranking_position(user_id: int, wallets: list[UserWallet]) -> int | None:
    for index, wallet in enumerate(wallets, start=1):
        if wallet.user_id == user_id:
            return index
    return None


def _ranking_medal(position: int | None) -> str:
    medals = {
        1: "🥇",
        2: "🥈",
        3: "🥉",
    }
    return medals.get(position or 0, "🏅")


def _reward_icon(reward: RewardItem) -> str:
    icons = {
        RewardType.ROLE: "🎭",
        RewardType.CUSTOM_TEXT: "📝",
        RewardType.MANUAL_REWARD: "🎁",
        RewardType.DIGITAL_CODE: "🔑",
        RewardType.VIP_ACCESS: "💎",
        RewardType.EVENT_ENTRY: "🎟️",
    }
    return icons.get(reward.type, "🛒")


def _format_reward_stock_short(reward: RewardItem) -> str:
    if reward.stock_quantity == 0:
        return "Esgotado"
    if reward.stock_quantity is None:
        return "Ilimitado"
    return f"{reward.stock_quantity} un."


def _format_reward_duration(duration_days: int | None) -> str:
    if duration_days is None:
        return "Permanente"
    if duration_days == 1:
        return "1 dia"
    return f"{duration_days} dias"


def _format_embed_lines(
    lines: list[str],
    *,
    limit: int = 1024,
    separator: str = "\n",
) -> str:
    value = ""
    shown = 0

    for line in lines:
        suffix = f"\n... e mais {len(lines) - shown}" if shown < len(lines) else ""
        candidate = f"{value}{separator}{line}" if value else line
        if len(candidate) + len(suffix) > limit:
            break

        value = candidate
        shown += 1

    if shown < len(lines):
        remaining = len(lines) - shown
        ellipsis = f"... e mais {remaining}"
        value = f"{value}{separator}{ellipsis}" if value else ellipsis

    return value or "-"
