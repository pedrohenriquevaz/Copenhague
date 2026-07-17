from __future__ import annotations

from typing import cast
from urllib.parse import urlsplit

import discord
from discord.ext import commands

from app.integrations.mlbb.dto import MlbbStatHighlightKind
from app.models.mlbb import (
    MlbbAchievement,
    MlbbAchievementsSnapshot,
    MlbbProfileSection,
    MlbbProfileSnapshot,
)
from app.services.mlbb_profile_service import (
    MlbbProfileAccessDeniedError,
    MlbbProfileFeatureDisabledError,
    MlbbProfileNotLinkedError,
    MlbbProfileProviderUnavailableError,
    MlbbProfileReauthenticationRequiredError,
    MlbbProfileRefreshCooldownError,
    MlbbProfileService,
    MlbbProfileServiceError,
)
from app.ui.mlbb_panel import MLBB_COLOR
from app.utils.mlbb_formatters import (
    NOT_AVAILABLE,
    format_duration_hours,
    format_highlight_value,
    format_optional_number,
    format_percentage,
    highlight_label,
    mask_game_id,
)

PROVIDER_ATTRIBUTION = "Dados: MLBB Public Data API comunitária e não oficial"


def build_mlbb_profile_embed(profile: MlbbProfileSnapshot) -> discord.Embed:
    embed = discord.Embed(
        title=_truncate(profile.player_name or "Perfil Mobile Legends", 256),
        description=(
            "Game ID mascarado: " f"{mask_game_id(profile.role_id, profile.zone_id)}"
        ),
        color=MLBB_COLOR,
    )
    embed.add_field(name="Nível", value=format_optional_number(profile.level))
    embed.add_field(
        name="País",
        value=_truncate(profile.country_code or NOT_AVAILABLE, 1024),
    )
    embed.add_field(name="Rank atual", value=_truncate(profile.current_rank, 1024))
    embed.add_field(
        name="Maior rank histórico",
        value=_truncate(profile.highest_rank, 1024),
    )
    embed.add_field(name="Partidas", value=format_optional_number(profile.matches))
    embed.add_field(name="Vitórias", value=format_optional_number(profile.wins))
    embed.add_field(name="Win Rate", value=format_percentage(profile.win_rate))
    embed.add_field(name="MVPs", value=format_optional_number(profile.mvp_count))
    embed.add_field(
        name="Dados atualizados",
        value=f"<t:{int(profile.updated_at.timestamp())}:R>",
        inline=False,
    )
    if _safe_image_url(profile.avatar_url):
        embed.set_thumbnail(url=cast(str, profile.avatar_url))
    cache_note = " • cache" if profile.from_cache else ""
    embed.set_footer(text=f"{PROVIDER_ATTRIBUTION}{cache_note}")
    return embed


def build_mlbb_achievements_embed(
    achievements: MlbbAchievementsSnapshot,
) -> discord.Embed:
    embed = discord.Embed(
        title=_truncate(
            f"Conquistas — {achievements.player_name or 'Mobile Legends'}",
            256,
        ),
        color=MLBB_COLOR,
    )
    embed.add_field(
        name="Maior sequência de vitórias",
        value=format_optional_number(achievements.longest_win_streak),
    )
    embed.add_field(
        name="Tempo jogado",
        value=format_duration_hours(achievements.game_time_hours),
    )
    embed.add_field(
        name="Score médio",
        value=format_optional_number(achievements.average_score),
    )
    first_hero_image: str | None = None
    for highlight in achievements.highlights[:7]:
        kind = _highlight_kind(highlight)
        if kind is None:
            continue
        embed.add_field(
            name=highlight_label(kind),
            value=_achievement_value(highlight, kind),
        )
        if first_hero_image is None and _safe_image_url(highlight.hero_image_url):
            first_hero_image = highlight.hero_image_url
    embed.add_field(
        name="Dados atualizados",
        value=f"<t:{int(achievements.updated_at.timestamp())}:R>",
        inline=False,
    )
    thumbnail = first_hero_image or achievements.avatar_url
    if _safe_image_url(thumbnail):
        embed.set_thumbnail(url=cast(str, thumbnail))
    cache_note = " • cache" if achievements.from_cache else ""
    embed.set_footer(text=f"{PROVIDER_ATTRIBUTION}{cache_note}")
    return embed


def mlbb_profile_error_message(error: MlbbProfileServiceError) -> str:
    if isinstance(error, MlbbProfileFeatureDisabledError):
        return "A integração MLBB está desativada neste ambiente."
    if isinstance(error, MlbbProfileNotLinkedError):
        return "Esta conta Discord não possui um vínculo MLBB ativo."
    if isinstance(error, MlbbProfileReauthenticationRequiredError):
        return (
            "A sessão MLBB precisa ser renovada. "
            "O dono da conta deve usar /mlbb reautenticar."
        )
    if isinstance(error, MlbbProfileAccessDeniedError):
        return "Este perfil MLBB é privado."
    if isinstance(error, MlbbProfileProviderUnavailableError):
        return "A API MLBB está indisponível. Tente novamente em instantes."
    if isinstance(error, MlbbProfileRefreshCooldownError):
        return f"Aguarde {error.retry_after_seconds}s " "antes de atualizar novamente."
    return "Não foi possível consultar os dados MLBB com segurança."


class MlbbProfileView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        requester_user_id: int,
        target_user_id: int,
        section: MlbbProfileSection,
    ) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.requester_user_id = requester_user_id
        self.target_user_id = target_user_id
        self.section = section
        self._sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_user_id:
            return True
        await interaction.response.send_message(
            "Este painel pertence a outra consulta.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Perfil", style=discord.ButtonStyle.secondary)
    async def profile_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._render(interaction, MlbbProfileSection.PROFILE)

    @discord.ui.button(label="Conquistas", style=discord.ButtonStyle.primary)
    async def achievements_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._render(interaction, MlbbProfileSection.ACHIEVEMENTS)

    @discord.ui.button(label="Atualizar", style=discord.ButtonStyle.success)
    async def refresh_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.requester_user_id != self.target_user_id:
            await interaction.response.send_message(
                "Somente o dono da conta pode forçar uma atualização.",
                ephemeral=True,
            )
            return
        await self._render(interaction, self.section, force_refresh=True)

    @discord.ui.button(label="Histórico", style=discord.ButtonStyle.secondary)
    async def history_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            "Histórico disponível em próxima fase.", ephemeral=True
        )

    @discord.ui.button(label="Heróis", style=discord.ButtonStyle.secondary)
    async def heroes_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            "Heróis frequentes disponíveis em próxima fase.", ephemeral=True
        )

    async def _render(
        self,
        interaction: discord.Interaction,
        section: MlbbProfileSection,
        *,
        force_refresh: bool = False,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este painel dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.defer()
        try:
            embed = await self._load_embed(
                interaction,
                section,
                force_refresh=force_refresh,
            )
        except MlbbProfileServiceError as exc:
            await interaction.followup.send(
                mlbb_profile_error_message(exc), ephemeral=True
            )
            return
        self.section = section
        self._sync_buttons()
        await interaction.edit_original_response(embed=embed, view=self)

    async def _load_embed(
        self,
        interaction: discord.Interaction,
        section: MlbbProfileSection,
        *,
        force_refresh: bool,
    ) -> discord.Embed:
        service = _profile_service(self.bot)
        common = {
            "guild_id": cast(int, interaction.guild_id),
            "requester_user_id": interaction.user.id,
            "target_user_id": self.target_user_id,
            "force_refresh": force_refresh,
        }
        if section is MlbbProfileSection.PROFILE:
            return build_mlbb_profile_embed(await service.get_profile(**common))
        return build_mlbb_achievements_embed(await service.get_achievements(**common))

    def _sync_buttons(self) -> None:
        self.profile_button.disabled = self.section is MlbbProfileSection.PROFILE
        self.achievements_button.disabled = (
            self.section is MlbbProfileSection.ACHIEVEMENTS
        )


def _profile_service(bot: commands.Bot) -> MlbbProfileService:
    return cast(
        MlbbProfileService,
        bot.mlbb_profile_service,  # type: ignore[attr-defined]
    )


def _achievement_value(
    achievement: MlbbAchievement,
    kind: MlbbStatHighlightKind,
) -> str:
    value = format_highlight_value(kind, achievement.value)
    hero = achievement.hero_name or NOT_AVAILABLE
    if _safe_image_url(achievement.hero_image_url) and achievement.hero_name:
        hero = f"{achievement.hero_name} | Imagem: {achievement.hero_image_url}"
    return _truncate(f"{value}\nHerói: {hero}", 1024)


def _highlight_kind(
    achievement: MlbbAchievement,
) -> MlbbStatHighlightKind | None:
    try:
        return MlbbStatHighlightKind(achievement.kind)
    except ValueError:
        return None


def _safe_image_url(value: str | None) -> bool:
    if not value or len(value) > 2048:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
