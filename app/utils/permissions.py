from __future__ import annotations

import discord


def has_manage_guild(member: discord.abc.User | discord.Member) -> bool:
    """Retorna se o usuario tem permissao de gerenciar servidor."""

    permissions = getattr(member, "guild_permissions", None)
    return bool(permissions and (permissions.manage_guild or permissions.administrator))


def has_administrator(member: discord.abc.User | discord.Member) -> bool:
    """Retorna se o usuario tem permissao administrativa."""

    permissions = getattr(member, "guild_permissions", None)
    return bool(permissions and permissions.administrator)


def has_role(member: discord.abc.User | discord.Member, role_id: int | None) -> bool:
    """Retorna se um membro possui um cargo especifico."""

    if role_id is None:
        return False

    roles = getattr(member, "roles", [])
    return any(getattr(role, "id", None) == role_id for role in roles)
