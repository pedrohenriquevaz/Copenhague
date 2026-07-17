from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.cogs.mlbb.admin import MlbbAdminController
from app.cogs.mlbb.profile import MlbbProfileController
from app.services.mlbb_auth_service import MlbbAuthService, MlbbAuthServiceError
from app.ui.mlbb_modals import mlbb_error_message
from app.ui.mlbb_panel import (
    MlbbCodeEntryView,
    MlbbPanelView,
    MlbbUnlinkConfirmView,
    build_mlbb_account_embed,
    build_mlbb_confirmation_embed,
)
from app.utils.permissions import has_manage_guild


class MlbbAccountCog(
    commands.GroupCog,
    group_name="mlbb",
    group_description="Vinculo seguro com Mobile Legends.",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(MlbbAuthService, bot.mlbb_auth_service)  # type: ignore[attr-defined]
        self.admin = MlbbAdminController(bot)
        self.profile_controller = MlbbProfileController(bot)

    @app_commands.command(
        name="vincular",
        description="Envia ao jogo o codigo para vincular sua conta.",
    )
    @app_commands.guild_only()
    @app_commands.describe(game_id="Seu Game ID.", area="Seu Zone ID/Area.")
    async def link(
        self,
        interaction: discord.Interaction,
        game_id: str,
        area: str,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self.service.start_link(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
                role_id=game_id,
                zone_id=area,
            )
        except MlbbAuthServiceError as exc:
            await interaction.followup.send(mlbb_error_message(exc), ephemeral=True)
            return
        await interaction.followup.send(
            "Codigo enviado ao correio interno do jogo. "
            f"A tentativa expira <t:{int(result.expires_at.timestamp())}:R>.",
            view=MlbbCodeEntryView(self.bot),
            ephemeral=True,
        )

    @app_commands.command(
        name="confirmar",
        description="Confirma o vinculo com o codigo recebido dentro do jogo.",
    )
    @app_commands.guild_only()
    async def confirm(self, interaction: discord.Interaction, codigo: str) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self.service.confirm_link(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
                verification_code=codigo,
            )
        except MlbbAuthServiceError as exc:
            await interaction.followup.send(mlbb_error_message(exc), ephemeral=True)
            return
        await interaction.followup.send(
            embed=build_mlbb_confirmation_embed(result), ephemeral=True
        )

    @app_commands.command(
        name="conta",
        description="Mostra o estado do seu vinculo Mobile Legends.",
    )
    @app_commands.guild_only()
    async def account(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            account = await self.service.get_account(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
            )
        except MlbbAuthServiceError as exc:
            await interaction.followup.send(mlbb_error_message(exc), ephemeral=True)
            return
        await interaction.followup.send(
            embed=build_mlbb_account_embed(account), ephemeral=True
        )

    @app_commands.command(
        name="desvincular",
        description="Revoga seu vinculo Mobile Legends apos confirmacao.",
    )
    @app_commands.guild_only()
    async def unlink(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "Confirma a revogacao local do seu vinculo MLBB?",
            view=MlbbUnlinkConfirmView(self.bot, interaction.user.id),
            ephemeral=True,
        )

    @app_commands.command(
        name="reautenticar",
        description="Renova uma conta marcada para reautenticacao.",
    )
    @app_commands.guild_only()
    async def reauthenticate(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self.service.start_reauthentication(
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

    @app_commands.command(
        name="perfil",
        description="Mostra o perfil e as estatísticas gerais de uma conta MLBB.",
    )
    @app_commands.guild_only()
    @app_commands.describe(membro="Membro do servidor; deixe vazio para ver o seu.")
    async def profile(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
    ) -> None:
        await self.profile_controller.show_profile(interaction, membro)

    @app_commands.command(
        name="conquistas",
        description="Mostra os melhores marcos gerais de uma conta MLBB.",
    )
    @app_commands.guild_only()
    @app_commands.describe(membro="Membro do servidor; deixe vazio para ver o seu.")
    async def achievements(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
    ) -> None:
        await self.profile_controller.show_achievements(interaction, membro)

    @app_commands.command(
        name="privacidade",
        description="Define quem pode consultar seu perfil MLBB neste servidor.",
    )
    @app_commands.guild_only()
    @app_commands.describe(valor="PRIVATE: só você; GUILD: membros do servidor.")
    @app_commands.choices(
        valor=[
            app_commands.Choice(name="PRIVATE — somente eu", value="PRIVATE"),
            app_commands.Choice(name="GUILD — este servidor", value="GUILD"),
        ]
    )
    async def privacy(
        self,
        interaction: discord.Interaction,
        valor: app_commands.Choice[str],
    ) -> None:
        await self.profile_controller.set_privacy(interaction, valor.value)

    @app_commands.command(
        name="painel_publicar",
        description="Publica o painel persistente de vinculo MLBB.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def publish_panel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return
        if not has_manage_guild(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para publicar este painel.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.admin.publish_panel(interaction, canal)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MlbbAccountCog(bot))
    bot.add_view(MlbbPanelView(bot))
