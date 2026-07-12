from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.services.truco_service import TrucoService, TrucoValidationError
from app.ui.truco_view import (
    TrucoLobbyView,
    TrucoTableView,
    build_truco_attachment,
    build_truco_embed,
    build_truco_message_kwargs,
)
from app.utils.permissions import has_administrator


class TrucoCog(commands.Cog):
    """Comandos do Truco Paulista."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(TrucoService, bot.truco_service)  # type: ignore[attr-defined]

    @app_commands.command(
        name="truco",
        description="Cria uma mesa de Truco Paulista 2x2 com aposta.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        parceiro="Membro que fará dupla com você.",
        adversario_1="Primeiro membro da dupla adversária.",
        adversario_2="Segundo membro da dupla adversária.",
        aposta="Valor apostado por cada jogador.",
    )
    async def truco(
        self,
        interaction: discord.Interaction,
        parceiro: discord.Member,
        adversario_1: discord.Member,
        adversario_2: discord.Member,
        aposta: int,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if interaction.channel is None:
            await interaction.response.send_message(
                "Não consegui identificar o canal da mesa.",
                ephemeral=True,
            )
            return
        if any(member.bot for member in (parceiro, adversario_1, adversario_2)):
            await interaction.response.send_message(
                "Bots não podem participar de partidas de Truco.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            session = await self.service.create_lobby(
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                created_by=interaction.user.id,
                partner_id=parceiro.id,
                opponent_1_id=adversario_1.id,
                opponent_2_id=adversario_2.id,
                stake=aposta,
            )
        except TrucoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        view = TrucoLobbyView(self.bot, session.id or 0, settings)
        display_names = {
            interaction.user.id: interaction.user.display_name,
            parceiro.id: parceiro.display_name,
            adversario_1.id: adversario_1.display_name,
            adversario_2.id: adversario_2.display_name,
        }
        try:
            message = await interaction.channel.send(
                embed=build_truco_embed(session, settings),
                file=build_truco_attachment(
                    session,
                    settings,
                    display_names=display_names,
                ),
                view=view,
            )
        except discord.HTTPException:
            await self.service.cancel_game(session.id or 0, interaction.user.id)
            await interaction.followup.send(
                "Não consegui publicar a mesa de Truco neste canal.",
                ephemeral=True,
            )
            return

        await self.service.attach_message(session.id or 0, message.id)
        await interaction.followup.send("Mesa de Truco criada.", ephemeral=True)

    @app_commands.command(
        name="truco_maquina",
        description="Jogue Truco individual contra a máquina.",
    )
    @app_commands.guild_only()
    async def truco_maquina(
        self,
        interaction: discord.Interaction,
        aposta: int,
    ) -> None:
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um canal de servidor.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            session = await self.service.create_pve_game(
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                created_by=interaction.user.id,
                stake=aposta,
            )
        except TrucoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        view = TrucoTableView(self.bot, session, settings)
        names = {
            interaction.user.id: interaction.user.display_name,
            self.service.MACHINE_USER_ID: "Máquina",
        }
        try:
            message = await interaction.channel.send(
                embed=build_truco_embed(session, settings),
                file=build_truco_attachment(
                    session,
                    settings,
                    display_names=names,
                ),
                view=view,
            )
        except discord.HTTPException:
            await self.service.cancel_game(session.id or 0, interaction.user.id)
            await interaction.followup.send(
                "Não consegui publicar a mesa de Truco neste canal.",
                ephemeral=True,
            )
            return
        await self.service.attach_message(session.id or 0, message.id)
        await interaction.followup.send(
            "Partida contra a máquina iniciada.", ephemeral=True
        )

    @app_commands.command(
        name="truco_cancelar_admin",
        description="Força o cancelamento das partidas de Truco de um usuário.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        usuario="Participante da partida que será cancelada.",
        motivo="Motivo administrativo do cancelamento.",
    )
    async def truco_cancelar_admin(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        motivo: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not has_administrator(interaction.user):
            await interaction.response.send_message(
                "Você não tem permissão para usar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            cancelled = await self.service.force_cancel_active_games(
                guild_id=interaction.guild.id,
                target_user_id=usuario.id,
                actor_id=interaction.user.id,
                reason=motivo,
            )
        except TrucoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        for session in cancelled:
            await self._update_cancelled_message(
                interaction.guild,
                session,
                settings,
            )

        refunded = sum(
            sum(not player.is_bot for player in session.players)
            for session in cancelled
            if session.accepted_user_ids == set(session.player_ids)
        )
        await interaction.followup.send(
            (
                "Cancelamento administrativo concluído.\n\n"
                f"Participante localizado: {usuario.mention}\n"
                f"Partidas canceladas: **{len(cancelled)}**\n"
                f"Apostas devolvidas: **{refunded}**\n"
                f"Motivo: {motivo.strip()}"
            ),
            ephemeral=True,
        )

    async def _update_cancelled_message(
        self,
        guild: discord.Guild,
        session,
        settings,
    ) -> None:
        if session.message_id is None:
            return
        channel = guild.get_channel(session.channel_id)
        if channel is None or not hasattr(channel, "fetch_message"):
            return
        try:
            message = await channel.fetch_message(session.message_id)
            names = {
                player.user_id: member.display_name
                for player in session.players
                if (member := guild.get_member(player.user_id)) is not None
            }
            await message.edit(
                **build_truco_message_kwargs(
                    session,
                    settings,
                    display_names=names,
                ),
                view=None,
            )
        except (discord.HTTPException, AttributeError):
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TrucoCog(bot))
