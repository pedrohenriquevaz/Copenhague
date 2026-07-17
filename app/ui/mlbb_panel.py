from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.mlbb import (
    MlbbAccountLinkStatus,
    MlbbAccountSummary,
    MlbbLinkConfirmationSummary,
)
from app.services.mlbb_auth_service import (
    MlbbAccountNotLinkedError,
    MlbbAuthService,
    MlbbAuthServiceError,
)
from app.ui.mlbb_modals import (
    MlbbLinkModal,
    MlbbVerificationCodeModal,
    mlbb_error_message,
)

MLBB_COLOR = discord.Color.from_rgb(57, 101, 181)


def build_mlbb_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Mobile Legends — Vincule sua conta",
        description=(
            "Conecte sua conta do jogo ao servidor de forma segura. "
            "O codigo de verificacao chega no correio interno do Mobile Legends; "
            "o bot nao altera a privacidade da sua conta dentro do jogo."
        ),
        color=MLBB_COLOR,
    )
    embed.add_field(
        name="Como funciona",
        value=(
            "1. Informe Game ID e Zone ID/Area.\n"
            "2. Consulte o correio dentro do jogo.\n"
            "3. Informe o codigo ao bot em ate 5 minutos."
        ),
        inline=False,
    )
    embed.set_footer(text="Dados fornecidos por uma API comunitaria e nao oficial.")
    return embed


def build_mlbb_account_embed(account: MlbbAccountSummary) -> discord.Embed:
    status_labels = {
        MlbbAccountLinkStatus.PENDING: "Aguardando confirmacao",
        MlbbAccountLinkStatus.ACTIVE: "Conta verificada",
        MlbbAccountLinkStatus.REAUTH_REQUIRED: "Reautenticacao necessaria",
        MlbbAccountLinkStatus.REVOKED: "Vinculo revogado",
    }
    embed = discord.Embed(
        title=account.player_name or "Conta Mobile Legends",
        description=status_labels[account.status],
        color=(
            discord.Color.orange()
            if account.status is MlbbAccountLinkStatus.REAUTH_REQUIRED
            else MLBB_COLOR
        ),
    )
    embed.add_field(name="Game ID", value=_mask_id(account.role_id))
    embed.add_field(name="Area", value=_mask_id(account.zone_id))
    embed.add_field(name="Visibilidade", value=account.visibility.value)
    if account.verified_at is not None:
        embed.add_field(
            name="Verificada",
            value=f"<t:{int(account.verified_at.timestamp())}:R>",
            inline=False,
        )
    if account.avatar_url:
        embed.set_thumbnail(url=account.avatar_url)
    embed.set_footer(text="Nenhuma credencial e exibida por este painel.")
    return embed


def build_mlbb_confirmation_embed(
    result: MlbbLinkConfirmationSummary,
) -> discord.Embed:
    embed = build_mlbb_account_embed(result.account)
    embed.title = result.account.player_name or "Conta Mobile Legends verificada"
    embed.description = (
        "Esta confirmacao ja havia sido concluida."
        if result.already_verified
        else "Conta vinculada com sucesso."
    )
    return embed


class MlbbPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Vincular conta",
        style=discord.ButtonStyle.primary,
        custom_id="mlbb:account:link",
    )
    async def link_account(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(MlbbLinkModal(self.bot))

    @discord.ui.button(
        label="Gerenciar vinculo",
        style=discord.ButtonStyle.secondary,
        custom_id="mlbb:account:manage",
    )
    async def manage_account(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este painel dentro de um servidor.", ephemeral=True
            )
            return
        service = _service(self.bot)
        try:
            account = await service.get_account(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
            )
        except MlbbAccountNotLinkedError:
            await interaction.response.send_message(
                "Voce ainda nao possui vinculo. Use **Vincular conta**.",
                ephemeral=True,
            )
            return
        except MlbbAuthServiceError as exc:
            await interaction.response.send_message(
                mlbb_error_message(exc), ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=build_mlbb_account_embed(account),
            view=MlbbManageView(self.bot, account, interaction.user.id),
            ephemeral=True,
        )


class MlbbCodeEntryView(discord.ui.View):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="Informar codigo", style=discord.ButtonStyle.success)
    async def enter_code(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(MlbbVerificationCodeModal(self.bot))


class MlbbManageView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        account: MlbbAccountSummary,
        owner_user_id: int,
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.account = account
        self.owner_user_id = owner_user_id
        self.reauthenticate.disabled = (
            account.status is not MlbbAccountLinkStatus.REAUTH_REQUIRED
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_user_id:
            return True
        await interaction.response.send_message(
            "Este painel pertence a outro membro.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Reautenticar", style=discord.ButtonStyle.primary)
    async def reauthenticate(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.guild_id is None:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await _service(self.bot).start_reauthentication(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
            )
        except MlbbAuthServiceError as exc:
            await interaction.followup.send(mlbb_error_message(exc), ephemeral=True)
            return
        await interaction.followup.send(
            "Novo codigo enviado ao jogo. "
            f"A tentativa expira <t:{int(result.expires_at.timestamp())}:R>.",
            view=MlbbCodeEntryView(self.bot),
            ephemeral=True,
        )

    @discord.ui.button(label="Desvincular", style=discord.ButtonStyle.danger)
    async def unlink(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            "Confirma a revogacao local deste vinculo?",
            view=MlbbUnlinkConfirmView(self.bot, interaction.user.id),
            ephemeral=True,
        )


class MlbbUnlinkConfirmView(discord.ui.View):
    def __init__(self, bot: commands.Bot, owner_user_id: int) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.owner_user_id = owner_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_user_id:
            return True
        await interaction.response.send_message(
            "Esta confirmacao pertence a outro membro.", ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Confirmar desvinculacao", style=discord.ButtonStyle.danger
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.guild_id is None:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await _service(self.bot).unlink(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
            )
        except MlbbAuthServiceError as exc:
            await interaction.followup.send(mlbb_error_message(exc), ephemeral=True)
            return
        await interaction.followup.send(
            "Vinculo MLBB removido localmente.", ephemeral=True
        )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Desvinculacao cancelada.", view=None
        )
        self.stop()


def _service(bot: commands.Bot) -> MlbbAuthService:
    return cast(MlbbAuthService, bot.mlbb_auth_service)  # type: ignore[attr-defined]


def _mask_id(value: int) -> str:
    raw = str(value)
    if len(raw) <= 4:
        return raw
    return "•" * (len(raw) - 4) + raw[-4:]
