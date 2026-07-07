from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from app.ui.bot_announcement import (
    BotAnnouncementView,
    build_bot_announcement_embed,
)
from app.utils.permissions import has_manage_guild


class UtilityCog(commands.Cog):
    """Comandos utilitarios de comunicacao do bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="anuncio_bot",
        description="Publica a embed de apresentacao do bot em um canal.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        canal="Canal onde o anuncio sera publicado.",
        imagem="Imagem exibida dentro da embed.",
    )
    async def publish_bot_announcement(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel | discord.Thread,
        imagem: discord.Attachment,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not has_manage_guild(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return
        if not _is_image_attachment(imagem):
            await interaction.response.send_message(
                "Anexe uma imagem valida para o anuncio.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        filename = _announcement_filename(imagem.filename)
        try:
            file = await imagem.to_file(filename=filename)
            message = await canal.send(
                embed=build_bot_announcement_embed(
                    image_url=f"attachment://{filename}"
                ),
                file=file,
                view=BotAnnouncementView(self.bot),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Nao tenho permissao para publicar neste canal.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Nao consegui publicar o anuncio do bot.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Anuncio publicado com sucesso: {message.jump_url}",
            ephemeral=True,
        )


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    if attachment.content_type and attachment.content_type.startswith("image/"):
        return True
    return Path(attachment.filename).suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
    }


def _announcement_filename(original_filename: str) -> str:
    suffix = Path(original_filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        suffix = ".png"
    return f"bot_anuncio{suffix}"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityCog(bot))
    bot.add_view(BotAnnouncementView(bot))
