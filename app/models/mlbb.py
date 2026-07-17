from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class MlbbAuthAttemptStatus(StrEnum):
    CREATED = "CREATED"
    CODE_SENT = "CODE_SENT"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MlbbAuthPurpose(StrEnum):
    LINK = "LINK"
    REAUTH = "REAUTH"


class MlbbAccountLinkStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    REVOKED = "REVOKED"


class MlbbProfileVisibility(StrEnum):
    PRIVATE = "PRIVATE"
    GUILD = "GUILD"
    PUBLIC = "PUBLIC"


class MlbbProfileSection(StrEnum):
    PROFILE = "PROFILE"
    ACHIEVEMENTS = "ACHIEVEMENTS"


class MlbbBeginAttemptOutcome(StrEnum):
    CREATED = "CREATED"
    COOLDOWN = "COOLDOWN"
    IN_PROGRESS = "IN_PROGRESS"
    ALREADY_LINKED = "ALREADY_LINKED"
    ACCOUNT_IN_USE = "ACCOUNT_IN_USE"
    REAUTH_NOT_ALLOWED = "REAUTH_NOT_ALLOWED"


class MlbbClaimAttemptOutcome(StrEnum):
    CLAIMED = "CLAIMED"
    NOT_FOUND = "NOT_FOUND"
    EXPIRED = "EXPIRED"
    TOO_MANY_ATTEMPTS = "TOO_MANY_ATTEMPTS"
    IN_PROGRESS = "IN_PROGRESS"
    ALREADY_VERIFIED = "ALREADY_VERIFIED"


class MlbbCompleteAttemptOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    ALREADY_VERIFIED = "ALREADY_VERIFIED"


@dataclass(frozen=True, slots=True)
class MlbbAuthAttempt:
    id: UUID
    guild_id: int
    discord_user_id: int
    role_id: int
    zone_id: int
    purpose: MlbbAuthPurpose
    status: MlbbAuthAttemptStatus
    attempts: int
    expires_at: datetime
    code_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MlbbAccountLink:
    guild_id: int
    discord_user_id: int
    role_id: int
    zone_id: int
    player_name: str | None
    avatar_url: str | None
    country_code: str | None
    encrypted_jwt: str | None = field(repr=False)
    status: MlbbAccountLinkStatus
    visibility: MlbbProfileVisibility
    verified_at: datetime | None
    last_validated_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MlbbBeginAttemptResult:
    outcome: MlbbBeginAttemptOutcome
    attempt: MlbbAuthAttempt | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class MlbbClaimAttemptResult:
    outcome: MlbbClaimAttemptOutcome
    attempt: MlbbAuthAttempt | None = None
    link: MlbbAccountLink | None = None


@dataclass(frozen=True, slots=True)
class MlbbCompleteAttemptResult:
    outcome: MlbbCompleteAttemptOutcome
    attempt: MlbbAuthAttempt
    link: MlbbAccountLink


@dataclass(frozen=True, slots=True)
class MlbbLinkStartSummary:
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MlbbAccountSummary:
    role_id: int
    zone_id: int
    player_name: str | None
    avatar_url: str | None
    country_code: str | None
    status: MlbbAccountLinkStatus
    visibility: MlbbProfileVisibility
    verified_at: datetime | None


@dataclass(frozen=True, slots=True)
class MlbbLinkConfirmationSummary:
    account: MlbbAccountSummary
    already_verified: bool = False


@dataclass(frozen=True, slots=True)
class MlbbUnlinkSummary:
    account: MlbbAccountSummary
    external_logout_succeeded: bool


@dataclass(frozen=True, slots=True)
class MlbbProfileAccess:
    guild_id: int
    requester_user_id: int
    target_user_id: int
    visibility: MlbbProfileVisibility

    @property
    def is_owner(self) -> bool:
        return self.requester_user_id == self.target_user_id


@dataclass(frozen=True, slots=True)
class MlbbProfileSnapshot:
    discord_user_id: int
    role_id: int
    zone_id: int
    player_name: str
    avatar_url: str | None
    level: int | None
    current_rank: str
    highest_rank: str
    matches: int
    wins: int
    win_rate: float
    mvp_count: int
    country_code: str | None
    visibility: MlbbProfileVisibility
    updated_at: datetime
    from_cache: bool


@dataclass(frozen=True, slots=True)
class MlbbAchievement:
    kind: str
    value: float
    occurred_at: int | None
    hero_name: str | None
    hero_image_url: str | None


@dataclass(frozen=True, slots=True)
class MlbbAchievementsSnapshot:
    discord_user_id: int
    player_name: str | None
    avatar_url: str | None
    longest_win_streak: int
    game_time_hours: float | None
    average_score: float | None
    highlights: tuple[MlbbAchievement, ...]
    visibility: MlbbProfileVisibility
    updated_at: datetime
    from_cache: bool
