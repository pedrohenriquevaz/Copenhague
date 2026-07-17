from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.mlbb import MlbbProfileSection, MlbbProfileVisibility
from app.services.mlbb_profile_service import (
    MlbbProfileService,
    MlbbProfileServiceError,
)
from app.ui.mlbb_profile_view import (
    MlbbProfileView,
    build_mlbb_achievements_embed,
    build_mlbb_profile_embed,
    mlbb_profile_error_message,
)


class MlbbProfileController:
    """Adapta interações Discord ao serviço de perfil MLBB."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(
            MlbbProfileService,
            bot.mlbb_profile_service,  # type: ignore[attr-defined]
        )

    async def show_profile(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None,
    ) -> None:
        context = await self._prepare_query(interaction, member)
        if context is None:
            return
        target_user_id, ephemeral = context
        try:
            profile = await self.service.get_profile(
                guild_id=cast(int, interaction.guild_id),
                requester_user_id=interaction.user.id,
                target_user_id=target_user_id,
            )
        except MlbbProfileServiceError as exc:
            await interaction.followup.send(
                mlbb_profile_error_message(exc), ephemeral=True
            )
            return
        await interaction.followup.send(
            embed=build_mlbb_profile_embed(profile),
            view=MlbbProfileView(
                self.bot,
                requester_user_id=interaction.user.id,
                target_user_id=target_user_id,
                section=MlbbProfileSection.PROFILE,
            ),
            ephemeral=ephemeral,
        )

    async def show_achievements(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None,
    ) -> None:
        context = await self._prepare_query(interaction, member)
        if context is None:
            return
        target_user_id, ephemeral = context
        try:
            achievements = await self.service.get_achievements(
                guild_id=cast(int, interaction.guild_id),
                requester_user_id=interaction.user.id,
                target_user_id=target_user_id,
            )
        except MlbbProfileServiceError as exc:
            await interaction.followup.send(
                mlbb_profile_error_message(exc), ephemeral=True
            )
            return
        await interaction.followup.send(
            embed=build_mlbb_achievements_embed(achievements),
            view=MlbbProfileView(
                self.bot,
                requester_user_id=interaction.user.id,
                target_user_id=target_user_id,
                section=MlbbProfileSection.ACHIEVEMENTS,
            ),
            ephemeral=ephemeral,
        )

    async def set_privacy(
        self,
        interaction: discord.Interaction,
        value: str,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            visibility = MlbbProfileVisibility(value)
            updated = await self.service.set_visibility(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
                visibility=visibility,
            )
        except (ValueError, MlbbProfileServiceError) as exc:
            message = (
                "Escolha PRIVATE ou GUILD."
                if isinstance(exc, ValueError)
                else mlbb_profile_error_message(exc)
            )
            await interaction.followup.send(message, ephemeral=True)
            return
        label = (
            "Somente você pode consultar seu perfil."
            if updated is MlbbProfileVisibility.PRIVATE
            else "Membros deste servidor podem consultar seu perfil."
        )
        await interaction.followup.send(label, ephemeral=True)

    async def _prepare_query(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None,
    ) -> tuple[int, bool] | None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return None
        target_user_id = member.id if member is not None else interaction.user.id
        try:
            access = await self.service.check_access(
                guild_id=interaction.guild_id,
                requester_user_id=interaction.user.id,
                target_user_id=target_user_id,
            )
        except MlbbProfileServiceError as exc:
            await interaction.response.send_message(
                mlbb_profile_error_message(exc), ephemeral=True
            )
            return None
        ephemeral = access.is_owner
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        return target_user_id, ephemeral
