from __future__ import annotations

import discord

from app.models.moderation import ModerationPrincipal


def moderation_principal(
    member: discord.Member,
    *,
    permissions: discord.Permissions | None = None,
) -> ModerationPrincipal:
    """Converte o estado atual do Discord em snapshot para o dominio."""
    effective_permissions = (
        permissions if permissions is not None else member.guild_permissions
    )
    enabled = frozenset(name for name, value in effective_permissions if value)
    return ModerationPrincipal(
        guild_id=member.guild.id,
        user_id=member.id,
        role_ids=frozenset(role.id for role in member.roles),
        top_role_position=member.top_role.position,
        top_role_id=member.top_role.id,
        native_permissions=enabled,
        is_owner=member.id == member.guild.owner_id,
        is_administrator=effective_permissions.administrator,
    )
