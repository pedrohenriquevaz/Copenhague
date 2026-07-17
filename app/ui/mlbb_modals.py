from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.services.mlbb_auth_service import (
    MlbbAccountInUseError,
    MlbbAlreadyLinkedError,
    MlbbAttemptExpiredError,
    MlbbAttemptNotFoundError,
    MlbbAuthService,
    MlbbAuthServiceError,
    MlbbCooldownError,
    MlbbFeatureDisabledError,
    MlbbInvalidCodeError,
    MlbbOperationInProgressError,
    MlbbProviderUnavailableError,
    MlbbReauthenticationNotAllowedError,
    MlbbTooManyAttemptsError,
    MlbbValidationError,
)


def mlbb_error_message(error: MlbbAuthServiceError) -> str:
    if isinstance(error, MlbbCooldownError):
        return (
            "Aguarde " f"{error.retry_after_seconds}s antes de solicitar outro codigo."
        )
    if isinstance(error, MlbbInvalidCodeError):
        return (
            "O codigo informado e invalido. "
            f"Restam {error.attempts_remaining} tentativa(s)."
        )
    if isinstance(error, MlbbAttemptExpiredError):
        return "O codigo ou a tentativa expirou. Solicite um novo codigo."
    if isinstance(error, MlbbTooManyAttemptsError):
        return "Limite de tentativas atingido. Solicite um novo codigo."
    if isinstance(error, MlbbAccountInUseError):
        return "Esta conta MLBB ja esta vinculada a outro membro deste servidor."
    if isinstance(error, MlbbAlreadyLinkedError):
        return "Voce ja possui uma conta MLBB vinculada neste servidor."
    if isinstance(error, MlbbProviderUnavailableError):
        return "A API MLBB esta indisponivel. Tente novamente em instantes."
    if isinstance(error, MlbbFeatureDisabledError):
        return "A integracao MLBB esta desabilitada neste ambiente."
    if isinstance(error, MlbbOperationInProgressError):
        return "Uma operacao MLBB ja esta em andamento. Aguarde a conclusao."
    if isinstance(error, MlbbReauthenticationNotAllowedError):
        return "Este vinculo nao esta aguardando reautenticacao."
    if isinstance(error, MlbbAttemptNotFoundError):
        return "Nenhuma tentativa aberta foi encontrada. Use /mlbb vincular."
    if isinstance(error, MlbbValidationError):
        return str(error)
    return str(error) or "Nao foi possivel concluir a operacao MLBB."


class MlbbLinkModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(title="Vincular conta Mobile Legends")
        self.bot = bot
        self.game_id = discord.ui.TextInput(
            label="Game ID",
            placeholder="Ex.: 123456789",
            min_length=1,
            max_length=19,
        )
        self.zone_id = discord.ui.TextInput(
            label="Zone ID / Area",
            placeholder="Ex.: 1234",
            min_length=1,
            max_length=19,
        )
        self.add_item(self.game_id)
        self.add_item(self.zone_id)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este fluxo dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        service = cast(MlbbAuthService, self.bot.mlbb_auth_service)  # type: ignore[attr-defined]
        try:
            result = await service.start_link(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
                role_id=self.game_id.value,
                zone_id=self.zone_id.value,
            )
        except MlbbAuthServiceError as exc:
            await interaction.followup.send(mlbb_error_message(exc), ephemeral=True)
            return
        from app.ui.mlbb_panel import MlbbCodeEntryView

        await interaction.followup.send(
            "Codigo enviado ao correio interno do jogo. "
            f"A tentativa expira <t:{int(result.expires_at.timestamp())}:R>.",
            view=MlbbCodeEntryView(self.bot),
            ephemeral=True,
        )


class MlbbVerificationCodeModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(title="Confirmar conta Mobile Legends")
        self.bot = bot
        self.verification_code = discord.ui.TextInput(
            label="Codigo de verificacao",
            placeholder="Codigo recebido dentro do jogo",
            min_length=1,
            max_length=32,
        )
        self.add_item(self.verification_code)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este fluxo dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        service = cast(MlbbAuthService, self.bot.mlbb_auth_service)  # type: ignore[attr-defined]
        try:
            result = await service.confirm_link(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
                verification_code=self.verification_code.value,
            )
        except MlbbAuthServiceError as exc:
            await interaction.followup.send(mlbb_error_message(exc), ephemeral=True)
            return
        from app.ui.mlbb_panel import build_mlbb_confirmation_embed

        await interaction.followup.send(
            embed=build_mlbb_confirmation_embed(result), ephemeral=True
        )
