from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


class ModerationActionType(StrEnum):
    BAN = "BAN"
    KICK = "KICK"
    MUTE = "MUTE"
    WARN = "WARN"
    PURGE = "PURGE"
    CONFIGURATION = "CONFIGURATION"


class ModerationCaseStatus(StrEnum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    REVOKED = "REVOKED"
    FAILED = "FAILED"


class ModerationCaseOrigin(StrEnum):
    COMMAND = "COMMAND"
    AUTOMATION = "AUTOMATION"
    API = "API"


@dataclass(frozen=True, slots=True)
class ModerationSettings:
    guild_id: int
    authorized_role_ids: tuple[int, ...] = ()
    log_channel_id: int | None = None


@dataclass(frozen=True, slots=True)
class ModerationCase:
    id: int
    guild_id: int
    action_type: ModerationActionType
    target_user_id: int
    moderator_user_id: int
    reason: str
    created_at: datetime
    duration: timedelta | None
    status: ModerationCaseStatus
    origin: ModerationCaseOrigin
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModerationCaseCreate:
    guild_id: int
    action_type: ModerationActionType
    target_user_id: int
    moderator_user_id: int
    reason: str
    duration: timedelta | None = None
    status: ModerationCaseStatus = ModerationCaseStatus.OPEN
    origin: ModerationCaseOrigin = ModerationCaseOrigin.COMMAND
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModerationPrincipal:
    guild_id: int
    user_id: int
    role_ids: frozenset[int]
    top_role_position: int
    top_role_id: int
    native_permissions: frozenset[str]
    is_owner: bool = False
    is_administrator: bool = False

    @property
    def hierarchy_rank(self) -> tuple[int, int]:
        """Replica o desempate do Discord: na mesma posicao, menor ID e maior."""
        return self.top_role_position, -self.top_role_id


@dataclass(frozen=True, slots=True)
class ModerationRoleReference:
    guild_id: int
    role_id: int
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class ModerationLogChannelReference:
    guild_id: int
    channel_id: int
    bot_can_view: bool
    bot_can_send: bool
    bot_can_embed: bool
