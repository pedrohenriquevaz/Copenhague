from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class MlbbLoginResult:
    jwt: str = field(repr=False)
    role_id: int
    zone_id: int
    authenticated_at: int | None


@dataclass(frozen=True, slots=True)
class MlbbPlayerProfile:
    role_id: int
    zone_id: int
    name: str
    avatar_url: str | None
    level: int | None
    current_rank_code: int | None
    highest_rank_code: int | None
    country_code: str | None


@dataclass(frozen=True, slots=True)
class MlbbHeroSummary:
    hero_id: int | None
    name: str | None
    image_url: str | None
    large_image_url: str | None


class MlbbStatHighlightKind(StrEnum):
    MOST_DAMAGE = "MOST_DAMAGE"
    HIGHEST_KILLS = "HIGHEST_KILLS"
    MOST_ASSISTS = "MOST_ASSISTS"
    HIGHEST_SCORE = "HIGHEST_SCORE"
    MOST_DAMAGE_TAKEN = "MOST_DAMAGE_TAKEN"
    MOST_GOLD = "MOST_GOLD"
    MOST_TOTAL_DAMAGE = "MOST_TOTAL_DAMAGE"


@dataclass(frozen=True, slots=True)
class MlbbStatHighlight:
    kind: MlbbStatHighlightKind
    value: float
    occurred_at: int | None
    hero: MlbbHeroSummary
    battle_id: str | None
    season_id: int | None


@dataclass(frozen=True, slots=True)
class MlbbPlayerStatsRaw:
    wins: int
    matches: int
    average_score_raw: float | None
    game_time_hours: float | None
    mvp_count: int
    longest_win_streak: int
    highlights: tuple[MlbbStatHighlight, ...]
    season_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MlbbPageInfo:
    next_cursor: str | None
    has_next: bool
    count: int


@dataclass(frozen=True, slots=True)
class MlbbMatch:
    battle_id: str
    season_id: int | None
    hero: MlbbHeroSummary
    kills: int | None
    deaths: int | None
    assists: int | None
    lane_id: int | None
    score_raw: float | None
    is_mvp: bool | None
    won: bool | None
    occurred_at: int | None


@dataclass(frozen=True, slots=True)
class MlbbMatchPage:
    matches: tuple[MlbbMatch, ...]
    page_info: MlbbPageInfo


@dataclass(frozen=True, slots=True)
class MlbbItemSummary:
    item_id: int | None
    name: str | None
    image_url: str | None
    large_image_url: str | None


@dataclass(frozen=True, slots=True)
class MlbbMatchParticipant:
    team: int | None
    role_id: int | None
    zone_id: int | None
    player_name: str | None
    hero: MlbbHeroSummary
    kills: int | None
    deaths: int | None
    assists: int | None
    team_fight_rate: float | None
    damage_dealt: int | None
    damage_share: float | None
    score_raw: float | None
    is_mvp: bool | None
    item_ids: tuple[int, ...]
    items: tuple[MlbbItemSummary, ...]
    hero_level: int | None
    occurred_at: int | None
    battle_duration_seconds: int | None
    won: bool | None


@dataclass(frozen=True, slots=True)
class MlbbMatchDetails:
    battle_id: str
    season_id: int
    participants: tuple[MlbbMatchParticipant, ...]


@dataclass(frozen=True, slots=True)
class MlbbFrequentHero:
    hero: MlbbHeroSummary
    matches: int
    wins: int
    average_score_raw: float | None
    rating_points: int | None
    rating_ratio: float | None
    power_score: int | None


@dataclass(frozen=True, slots=True)
class MlbbHeroPage:
    heroes: tuple[MlbbFrequentHero, ...]
    page_info: MlbbPageInfo
