from __future__ import annotations

from io import BytesIO
from typing import cast

import discord
from discord.ext import commands

from app.models.uno import UnoCard, UnoColor, UnoGameStatus, UnoPlayer, UnoSession
from app.services.uno_service import UnoService, UnoValidationError
from app.ui.uno_table_image import UNO_TABLE_FILENAME, render_uno_table_image
from app.utils.permissions import has_administrator

HAND_PAGE_SIZE = 20
_OPEN_UNO_HANDS: dict[
    int,
    dict[
        int,
        discord.Interaction | discord.Message | discord.WebhookMessage,
    ],
] = {}


def build_uno_embed(session: UnoSession) -> discord.Embed:
    color = discord.Color.dark_green()
    if session.status is UnoGameStatus.LOBBY:
        color = discord.Color.blurple()
    elif session.status is UnoGameStatus.FINISHED:
        color = discord.Color.gold()
    elif session.status is UnoGameStatus.CANCELLED:
        color = discord.Color.red()
    embed = discord.Embed(title=session.title, color=color)
    embed.description = _public_description(session)
    embed.set_image(url=f"attachment://{UNO_TABLE_FILENAME}")
    return embed


def build_uno_attachment(
    session: UnoSession,
    *,
    display_names: dict[int, str] | None = None,
) -> discord.File:
    image = render_uno_table_image(session, display_names=display_names)
    return discord.File(BytesIO(image), filename=UNO_TABLE_FILENAME)


def build_uno_message_kwargs(
    session: UnoSession,
    *,
    display_names: dict[int, str] | None = None,
) -> dict[str, object]:
    return {
        "embed": build_uno_embed(session),
        "attachments": [build_uno_attachment(session, display_names=display_names)],
    }


class UnoLobbyView(discord.ui.View):
    def __init__(self, bot: commands.Bot, session: UnoSession) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.game_id = session.id or 0

    @discord.ui.button(
        label="Entrar",
        style=discord.ButtonStyle.success,
        custom_id="uno:lobby:join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run(interaction, "join")

    @discord.ui.button(
        label="Sair",
        style=discord.ButtonStyle.secondary,
        custom_id="uno:lobby:leave",
    )
    async def leave(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run(interaction, "leave")

    @discord.ui.button(
        label="Iniciar",
        style=discord.ButtonStyle.primary,
        custom_id="uno:lobby:start",
    )
    async def start(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run(interaction, "start")

    @discord.ui.button(
        label="Encerrar",
        style=discord.ButtonStyle.danger,
        custom_id="uno:lobby:cancel",
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run(interaction, "cancel")

    async def _run(self, interaction: discord.Interaction, action: str) -> None:
        service = cast(UnoService, self.bot.uno_service)  # type: ignore[attr-defined]
        await interaction.response.defer(ephemeral=True)
        try:
            if action == "join":
                session = await service.join_game(self.game_id, interaction.user.id)
            elif action == "leave":
                session = await service.leave_game(self.game_id, interaction.user.id)
            elif action == "start":
                session = await service.start_game(self.game_id, interaction.user.id)
            else:
                session = await service.cancel_game(
                    self.game_id,
                    interaction.user.id,
                    is_admin=has_administrator(interaction.user),
                )
        except UnoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await edit_uno_public_message(self.bot, session)
        message = {
            "join": "Você entrou na partida.",
            "leave": "Você saiu da partida.",
            "start": "Partida iniciada.",
            "cancel": "Partida encerrada.",
        }[action]
        await interaction.followup.send(message, ephemeral=True)


class UnoGameView(discord.ui.View):
    def __init__(self, bot: commands.Bot, session: UnoSession) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.game_id = session.id or 0
        self.session = session
        self._refresh_buttons()

    @discord.ui.button(
        label="Olhar Cartas",
        style=discord.ButtonStyle.primary,
        custom_id="uno:game:hand",
    )
    async def hand(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        service = cast(UnoService, self.bot.uno_service)  # type: ignore[attr-defined]
        session = await service.get_game(self.game_id)
        if session is None or session.player(interaction.user.id) is None:
            await interaction.response.send_message(
                "Você não participa desta partida.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=build_uno_hand_embed(session, interaction.user.id, page=0),
            view=UnoHandView(self.bot, session, interaction.user.id, page=0),
            ephemeral=True,
        )
        _register_uno_hand(self.game_id, interaction.user.id, interaction)

    @discord.ui.button(
        label="Comprar Carta",
        style=discord.ButtonStyle.success,
        custom_id="uno:game:draw",
    )
    async def draw(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _run_draw(self.bot, self.game_id, interaction, private=False)

    @discord.ui.button(
        label="Passar",
        style=discord.ButtonStyle.secondary,
        custom_id="uno:game:pass",
    )
    async def pass_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _run_pass(self.bot, self.game_id, interaction, private=False)

    @discord.ui.button(
        label="Encerrar Partida",
        style=discord.ButtonStyle.danger,
        custom_id="uno:game:cancel",
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        service = cast(UnoService, self.bot.uno_service)  # type: ignore[attr-defined]
        await interaction.response.defer(ephemeral=True)
        try:
            session = await service.cancel_game(
                self.game_id,
                interaction.user.id,
                is_admin=has_administrator(interaction.user),
            )
        except UnoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await edit_uno_public_message(self.bot, session)
        await interaction.followup.send("Partida encerrada.", ephemeral=True)

    def _refresh_buttons(self) -> None:
        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.custom_id == "uno:game:pass":
                item.disabled = self.session.drawn_card_id is None


class UnoHandView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        session: UnoSession,
        user_id: int,
        *,
        page: int,
    ) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.game_id = session.id or 0
        self.user_id = user_id
        self.page = _clamp_page(session, user_id, page)
        player = session.player(user_id)
        cards = player.hand if player else []
        page_cards = cards[
            self.page * HAND_PAGE_SIZE : (self.page + 1) * HAND_PAGE_SIZE
        ]
        self.add_item(UnoCardSelect(page_cards))
        self._refresh_buttons(session, len(cards))

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, row=1)
    async def previous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._change_page(interaction, self.page - 1)

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._change_page(interaction, self.page + 1)

    @discord.ui.button(
        label="Comprar Carta",
        style=discord.ButtonStyle.success,
        row=2,
    )
    async def draw(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _run_draw(self.bot, self.game_id, interaction, private=True)

    @discord.ui.button(label="Passar", style=discord.ButtonStyle.secondary, row=2)
    async def pass_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _run_pass(self.bot, self.game_id, interaction, private=True)

    async def _change_page(
        self,
        interaction: discord.Interaction,
        page: int,
    ) -> None:
        _register_uno_hand(self.game_id, self.user_id, interaction)
        service = cast(UnoService, self.bot.uno_service)  # type: ignore[attr-defined]
        session = await service.get_game(self.game_id)
        if session is None:
            await interaction.response.send_message(
                "Partida não encontrada.", ephemeral=True
            )
            return
        safe_page = _clamp_page(session, self.user_id, page)
        await interaction.response.edit_message(
            embed=build_uno_hand_embed(session, self.user_id, page=safe_page),
            view=UnoHandView(
                self.bot,
                session,
                self.user_id,
                page=safe_page,
            ),
        )

    def _refresh_buttons(self, session: UnoSession, card_count: int) -> None:
        total_pages = max(1, (card_count + HAND_PAGE_SIZE - 1) // HAND_PAGE_SIZE)
        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.label == "Anterior":
                item.disabled = self.page <= 0
            elif item.label == "Próxima":
                item.disabled = self.page + 1 >= total_pages
            elif item.label == "Passar":
                item.disabled = session.drawn_card_id is None


class UnoCardSelect(discord.ui.Select):
    def __init__(self, cards: list[UnoCard]) -> None:
        options = [
            discord.SelectOption(
                label=card.label[:100],
                value=str(card.id),
                emoji=card.color.symbol if card.color else "🌈",
            )
            for card in cards
        ]
        if not options:
            options = [discord.SelectOption(label="Sem cartas", value="empty")]
        super().__init__(
            placeholder="Escolha uma carta para jogar",
            options=options,
            min_values=1,
            max_values=1,
            disabled=not cards,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = cast(UnoHandView, self.view)
        _register_uno_hand(view.game_id, view.user_id, interaction)
        if interaction.user.id != view.user_id:
            await interaction.response.send_message(
                "Esta mão pertence a outro jogador.",
                ephemeral=True,
            )
            return
        card_id = int(self.values[0])
        service = cast(UnoService, view.bot.uno_service)  # type: ignore[attr-defined]
        session = await service.get_game(view.game_id)
        player = session.player(view.user_id) if session else None
        card = (
            next((item for item in player.hand if item.id == card_id), None)
            if player
            else None
        )
        if session is None or card is None:
            await interaction.response.send_message(
                "Essa carta não está mais disponível.",
                ephemeral=True,
            )
            return
        if card.value.is_wild:
            await interaction.response.edit_message(
                embed=build_uno_color_embed(card),
                view=UnoColorView(
                    view.bot,
                    session,
                    view.user_id,
                    card_id=card.id,
                    page=view.page,
                ),
            )
            return
        await _play_selected_card(
            view.bot,
            session,
            interaction,
            user_id=view.user_id,
            card_id=card.id,
            page=view.page,
        )


class UnoColorView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        session: UnoSession,
        user_id: int,
        *,
        card_id: int,
        page: int,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.session = session
        self.user_id = user_id
        self.card_id = card_id
        self.page = page

    @discord.ui.button(label="Vermelho", style=discord.ButtonStyle.danger)
    async def red(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._choose(interaction, UnoColor.RED)

    @discord.ui.button(label="Azul", style=discord.ButtonStyle.primary)
    async def blue(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._choose(interaction, UnoColor.BLUE)

    @discord.ui.button(label="Verde", style=discord.ButtonStyle.success)
    async def green(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._choose(interaction, UnoColor.GREEN)

    @discord.ui.button(label="Amarelo", style=discord.ButtonStyle.secondary)
    async def yellow(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._choose(interaction, UnoColor.YELLOW)

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        _register_uno_hand(self.session.id or 0, self.user_id, interaction)
        await interaction.response.edit_message(
            embed=build_uno_hand_embed(self.session, self.user_id, page=self.page),
            view=UnoHandView(
                self.bot,
                self.session,
                self.user_id,
                page=self.page,
            ),
        )

    async def _choose(
        self,
        interaction: discord.Interaction,
        color: UnoColor,
    ) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Esta escolha pertence a outro jogador.",
                ephemeral=True,
            )
            return
        await _play_selected_card(
            self.bot,
            self.session,
            interaction,
            user_id=self.user_id,
            card_id=self.card_id,
            page=self.page,
            chosen_color=color,
        )


def build_uno_hand_embed(
    session: UnoSession,
    user_id: int,
    *,
    page: int,
) -> discord.Embed:
    player = session.player(user_id)
    cards = player.hand if player else []
    safe_page = _clamp_page(session, user_id, page)
    total_pages = max(1, (len(cards) + HAND_PAGE_SIZE - 1) // HAND_PAGE_SIZE)
    page_cards = cards[safe_page * HAND_PAGE_SIZE : (safe_page + 1) * HAND_PAGE_SIZE]
    lines = [
        f"`{index + 1:02}` {card.short_label}"
        + (" · **comprada**" if card.id == session.drawn_card_id else "")
        for index, card in enumerate(page_cards, start=safe_page * HAND_PAGE_SIZE)
    ]
    current = session.current_player
    turn = (
        "É sua vez." if current and current.user_id == user_id else "Aguarde sua vez."
    )
    embed = discord.Embed(title="Sua mão de UNO", color=discord.Color.dark_green())
    embed.description = (
        f"{turn} · **{len(cards)} carta(s)** · Página {safe_page + 1}/{total_pages}\n\n"
        + ("\n".join(lines) if lines else "Sua mão está vazia.")
    )
    if session.current_color is not None:
        action = session.last_action
        for participant in session.players:
            replacement = (
                "Máquina"
                if participant.is_bot
                else "Você" if participant.user_id == user_id else "Outro jogador"
            )
            action = action.replace(f"<@{participant.user_id}>", replacement)
        embed.set_footer(text=f"Cor atual: {session.current_color.label} · {action}")
    return embed


def build_uno_color_embed(card: UnoCard) -> discord.Embed:
    return discord.Embed(
        title="Escolha a nova cor",
        description=f"Carta selecionada: **{card.short_label}**",
        color=discord.Color.dark_grey(),
    )


async def _play_selected_card(
    bot: commands.Bot,
    session: UnoSession,
    interaction: discord.Interaction,
    *,
    user_id: int,
    card_id: int,
    page: int,
    chosen_color: UnoColor | None = None,
) -> None:
    service = cast(UnoService, bot.uno_service)  # type: ignore[attr-defined]
    _register_uno_hand(session.id or 0, user_id, interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        updated = await service.play_card(
            game_id=session.id or 0,
            user_id=user_id,
            card_id=card_id,
            chosen_color=chosen_color,
        )
    except UnoValidationError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    updated = await edit_uno_public_message(bot, updated)
    if updated.status is UnoGameStatus.FINISHED:
        channel = interaction.channel
        if channel is not None and hasattr(channel, "send"):
            try:
                await channel.send(f"<@{user_id}> venceu a partida de UNO!")
            except discord.HTTPException:
                pass


async def _run_draw(
    bot: commands.Bot,
    game_id: int,
    interaction: discord.Interaction,
    *,
    private: bool,
) -> None:
    service = cast(UnoService, bot.uno_service)  # type: ignore[attr-defined]
    if private:
        _register_uno_hand(game_id, interaction.user.id, interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        session = await service.draw_card(game_id, interaction.user.id)
    except UnoValidationError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    session = await edit_uno_public_message(bot, session)
    if not private:
        message = await interaction.followup.send(
            embed=build_uno_hand_embed(session, interaction.user.id, page=0),
            view=UnoHandView(bot, session, interaction.user.id, page=0),
            ephemeral=True,
            wait=True,
        )
        _register_uno_hand(game_id, interaction.user.id, message)


async def _run_pass(
    bot: commands.Bot,
    game_id: int,
    interaction: discord.Interaction,
    *,
    private: bool,
) -> None:
    service = cast(UnoService, bot.uno_service)  # type: ignore[attr-defined]
    if private:
        _register_uno_hand(game_id, interaction.user.id, interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        session = await service.pass_turn(game_id, interaction.user.id)
    except UnoValidationError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    session = await edit_uno_public_message(bot, session)
    if not private:
        await interaction.followup.send("Turno passado.", ephemeral=True)


async def edit_uno_public_message(
    bot: commands.Bot,
    session: UnoSession,
) -> UnoSession:
    service = cast(UnoService, bot.uno_service)  # type: ignore[attr-defined]
    was_playing = session.status is UnoGameStatus.PLAYING
    session = await service.play_machine_turns(session.id or 0)
    if session.message_id is None:
        await refresh_open_uno_hands(bot, session)
        return session
    channel = bot.get_channel(session.channel_id)
    if channel is None or not hasattr(channel, "fetch_message"):
        await refresh_open_uno_hands(bot, session)
        return session
    try:
        message = await channel.fetch_message(session.message_id)
        names = _display_names(bot, session)
        if session.status is UnoGameStatus.LOBBY:
            view: discord.ui.View | None = UnoLobbyView(bot, session)
        elif session.status is UnoGameStatus.PLAYING:
            view = UnoGameView(bot, session)
        else:
            view = None
        await message.edit(
            **build_uno_message_kwargs(session, display_names=names),
            view=view,
        )
    except discord.NotFound:
        await service.cancel_deleted_message(session.message_id)
    except (discord.HTTPException, AttributeError):
        pass
    await refresh_open_uno_hands(bot, session)
    if was_playing and session.status is UnoGameStatus.FINISHED:
        winner = session.player(session.winner_user_id or 0)
        if winner and winner.is_bot:
            channel = bot.get_channel(session.channel_id)
            if channel is not None and hasattr(channel, "send"):
                try:
                    await channel.send("A Máquina venceu a partida de UNO.")
                except discord.HTTPException:
                    pass
    return session


async def refresh_open_uno_hands(bot: commands.Bot, session: UnoSession) -> None:
    if session.id is None:
        return
    messages = _OPEN_UNO_HANDS.get(session.id, {})
    stale: list[int] = []
    for user_id, handle in list(messages.items()):
        player = session.player(user_id)
        if player is None:
            stale.append(user_id)
            continue
        view: discord.ui.View | None = None
        if session.status is UnoGameStatus.PLAYING:
            view = UnoHandView(bot, session, user_id, page=0)
        try:
            await _edit_uno_hand_handle(
                handle,
                build_uno_hand_embed(session, user_id, page=0),
                view,
            )
        except discord.HTTPException:
            stale.append(user_id)
    for user_id in stale:
        messages.pop(user_id, None)
    if session.status is not UnoGameStatus.PLAYING:
        _OPEN_UNO_HANDS.pop(session.id, None)


def _register_uno_hand(
    game_id: int,
    user_id: int,
    handle: discord.Interaction | discord.Message | discord.WebhookMessage,
) -> None:
    _OPEN_UNO_HANDS.setdefault(game_id, {})[user_id] = handle


async def _edit_uno_hand_handle(
    handle: discord.Interaction | discord.Message | discord.WebhookMessage,
    embed: discord.Embed,
    view: discord.ui.View | None,
) -> None:
    if isinstance(handle, discord.Interaction):
        await handle.edit_original_response(embed=embed, view=view)
        return
    await handle.edit(embed=embed, view=view)


def _public_description(session: UnoSession) -> str:
    if session.status is UnoGameStatus.LOBBY:
        players = ", ".join(_uno_player_reference(player) for player in session.players)
        return f"Jogadores: {players}\nCriador: <@{session.created_by}>"
    if session.status is UnoGameStatus.FINISHED:
        winner = session.player(session.winner_user_id or 0)
        return f"Vencedor: {_uno_player_reference(winner) if winner else '-'}"
    if session.status is UnoGameStatus.CANCELLED:
        return session.last_action
    current = session.current_player
    return (
        f"Vez de {_uno_player_reference(current)} · {session.last_action}"
        if current
        else "-"
    )


def _display_names(bot: commands.Bot, session: UnoSession) -> dict[int, str]:
    guild = bot.get_guild(session.guild_id)
    if guild is None:
        return {}
    names: dict[int, str] = {}
    for player in session.players:
        if player.is_bot:
            names[player.user_id] = "Máquina"
            continue
        member = guild.get_member(player.user_id)
        if member is not None:
            names[player.user_id] = member.display_name
    return names


def _uno_player_reference(player: UnoPlayer) -> str:
    return "Máquina" if player.is_bot else f"<@{player.user_id}>"


def _clamp_page(session: UnoSession, user_id: int, page: int) -> int:
    player = session.player(user_id)
    count = len(player.hand) if player else 0
    last_page = max(0, (count - 1) // HAND_PAGE_SIZE)
    return max(0, min(page, last_page))
