from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .dto import (
    MlbbFrequentHero,
    MlbbHeroPage,
    MlbbHeroSummary,
    MlbbItemSummary,
    MlbbLoginResult,
    MlbbMatch,
    MlbbMatchDetails,
    MlbbMatchPage,
    MlbbMatchParticipant,
    MlbbPageInfo,
    MlbbPlayerProfile,
    MlbbPlayerStatsRaw,
    MlbbStatHighlight,
    MlbbStatHighlightKind,
)
from .errors import MlbbInvalidResponseError

_HIGHLIGHT_FIELDS = {
    "mo": MlbbStatHighlightKind.MOST_DAMAGE,
    "hk": MlbbStatHighlightKind.HIGHEST_KILLS,
    "ma": MlbbStatHighlightKind.MOST_ASSISTS,
    "ms": MlbbStatHighlightKind.HIGHEST_SCORE,
    "mdt": MlbbStatHighlightKind.MOST_DAMAGE_TAKEN,
    "mg": MlbbStatHighlightKind.MOST_GOLD,
    "mtd": MlbbStatHighlightKind.MOST_TOTAL_DAMAGE,
}


def map_login(payload: Mapping[str, Any]) -> MlbbLoginResult:
    data = _required_mapping(payload, "data")
    jwt = _required_string(data, "jwt")
    return MlbbLoginResult(
        jwt=jwt,
        role_id=_required_int(data, "roleid"),
        zone_id=_required_int(data, "zoneid"),
        authenticated_at=_optional_int(data, "time"),
    )


def map_player_profile(payload: Mapping[str, Any]) -> MlbbPlayerProfile:
    data = _required_mapping(payload, "data")
    return MlbbPlayerProfile(
        role_id=_required_int(data, "roleId"),
        zone_id=_required_int(data, "zoneId"),
        name=_required_string(data, "name"),
        avatar_url=_optional_string(data, "avatar"),
        level=_optional_int(data, "level"),
        current_rank_code=_optional_int(data, "rank_level"),
        highest_rank_code=_optional_int(data, "history_rank_level"),
        country_code=_optional_string(data, "reg_country"),
    )


def map_player_stats(payload: Mapping[str, Any]) -> MlbbPlayerStatsRaw:
    data = _required_mapping(payload, "data")
    highlights: list[MlbbStatHighlight] = []
    for field_name, kind in _HIGHLIGHT_FIELDS.items():
        raw = data.get(field_name)
        if raw is None:
            continue
        highlight = _mapping_value(raw, field_name)
        value = _optional_number(highlight, "v")
        if value is None:
            continue
        highlights.append(
            MlbbStatHighlight(
                kind=kind,
                value=value,
                occurred_at=_optional_int(highlight, "ts"),
                hero=_map_hero(
                    highlight.get("hid_e"),
                    fallback_id=_optional_int(highlight, "hid"),
                ),
                battle_id=_optional_battle_id(highlight),
                season_id=_optional_int(highlight, "sid"),
            )
        )

    season_ids = _int_tuple(data.get("sids"), field_name="sids", default=())
    return MlbbPlayerStatsRaw(
        wins=_optional_int(data, "wc", default=0) or 0,
        matches=_optional_int(data, "tc", default=0) or 0,
        average_score_raw=_optional_number(data, "as"),
        game_time_hours=_optional_number(data, "gt"),
        mvp_count=_optional_int(data, "mvpc", default=0) or 0,
        longest_win_streak=_optional_int(data, "wsc", default=0) or 0,
        highlights=tuple(highlights),
        season_ids=season_ids,
    )


def map_seasons(payload: Mapping[str, Any]) -> tuple[int, ...]:
    data = _required_mapping(payload, "data")
    if "sids" not in data:
        raise _invalid("Campo obrigatorio ausente: data.sids.")
    return _int_tuple(data["sids"], field_name="sids")


def map_match_page(payload: Mapping[str, Any]) -> MlbbMatchPage:
    data = _required_mapping(payload, "data")
    raw_matches = _required_sequence(data, "result")
    matches = tuple(
        _map_match(_mapping_value(item, "result[]")) for item in raw_matches
    )
    return MlbbMatchPage(
        matches=matches,
        page_info=_map_page_info(data.get("pageInfo"), fallback_count=len(matches)),
    )


def map_match_details(
    payload: Mapping[str, Any],
    *,
    season_id: int,
    match_id: int | str,
) -> MlbbMatchDetails:
    data = _required_mapping(payload, "data")
    raw_participants = _required_sequence(data, "result")
    participants = tuple(
        _map_participant(_mapping_value(item, "result[]")) for item in raw_participants
    )
    return MlbbMatchDetails(
        battle_id=_battle_id_value(match_id, field_name="match_id"),
        season_id=season_id,
        participants=participants,
    )


def map_frequent_heroes(payload: Mapping[str, Any]) -> MlbbHeroPage:
    data = _required_mapping(payload, "data")
    raw_heroes = _required_sequence(data, "result")
    heroes = tuple(
        _map_frequent_hero(_mapping_value(item, "result[]")) for item in raw_heroes
    )
    return MlbbHeroPage(
        heroes=heroes,
        page_info=_map_page_info(data.get("pageInfo"), fallback_count=len(heroes)),
    )


def _map_match(data: Mapping[str, Any]) -> MlbbMatch:
    return MlbbMatch(
        battle_id=_required_battle_id(data),
        season_id=_optional_int(data, "sid"),
        hero=_map_hero(data.get("hid_e"), fallback_id=_optional_int(data, "hid")),
        kills=_optional_int(data, "k"),
        deaths=_optional_int(data, "d"),
        assists=_optional_int(data, "a"),
        lane_id=_optional_int(data, "lid"),
        score_raw=_optional_number(data, "s"),
        is_mvp=_optional_flag(data, "mvp"),
        won=_optional_flag(data, "res"),
        occurred_at=_optional_int(data, "ts"),
    )


def _map_participant(data: Mapping[str, Any]) -> MlbbMatchParticipant:
    raw_items = data.get("its_e")
    items: tuple[MlbbItemSummary, ...] = ()
    if raw_items is not None:
        item_values = _sequence_value(raw_items, "its_e")
        items = tuple(
            _map_item(_mapping_value(item, "its_e[]"))
            for item in item_values
            if item is not None
        )

    return MlbbMatchParticipant(
        team=_optional_int(data, "f"),
        role_id=_optional_int(data, "rid"),
        zone_id=_optional_int(data, "zid"),
        player_name=_optional_string(data, "rname"),
        hero=_map_hero(data.get("hid_e"), fallback_id=_optional_int(data, "hid")),
        kills=_optional_int(data, "k"),
        deaths=_optional_int(data, "d"),
        assists=_optional_int(data, "a"),
        team_fight_rate=_optional_number(data, "tfr"),
        damage_dealt=_optional_int(data, "o"),
        damage_share=_optional_number(data, "op"),
        score_raw=_optional_number(data, "s"),
        is_mvp=_optional_flag(data, "mvp"),
        item_ids=_int_tuple(data.get("its"), field_name="its", default=()),
        items=items,
        hero_level=_optional_int(data, "hlvl"),
        occurred_at=_optional_int(data, "ts"),
        battle_duration_seconds=_optional_int(data, "bd"),
        won=_optional_flag(data, "fw"),
    )


def _map_frequent_hero(data: Mapping[str, Any]) -> MlbbFrequentHero:
    return MlbbFrequentHero(
        hero=_map_hero(data.get("hid_e"), fallback_id=_optional_int(data, "hid")),
        matches=_optional_int(data, "tc", default=0) or 0,
        wins=_optional_int(data, "wc", default=0) or 0,
        average_score_raw=_optional_number(data, "bs"),
        rating_points=_optional_int(data, "mr"),
        rating_ratio=_optional_number(data, "mrp"),
        power_score=_optional_int(data, "p"),
    )


def _map_hero(raw: object, *, fallback_id: int | None) -> MlbbHeroSummary:
    if raw is None:
        return MlbbHeroSummary(fallback_id, None, None, None)
    data = _mapping_value(raw, "hid_e")
    return MlbbHeroSummary(
        hero_id=_optional_int(data, "id", default=fallback_id),
        name=_optional_string(data, "n"),
        image_url=_optional_string(data, "ix"),
        large_image_url=_optional_string(data, "i2x"),
    )


def _map_item(data: Mapping[str, Any]) -> MlbbItemSummary:
    return MlbbItemSummary(
        item_id=_optional_int(data, "id"),
        name=_optional_string(data, "n"),
        image_url=_optional_string(data, "ix"),
        large_image_url=_optional_string(data, "i2x"),
    )


def _map_page_info(raw: object, *, fallback_count: int) -> MlbbPageInfo:
    if raw is None:
        return MlbbPageInfo(None, False, fallback_count)
    data = _mapping_value(raw, "pageInfo")
    next_cursor = _optional_cursor(data.get("nextCursor"), "pageInfo.nextCursor")
    has_next = data.get("hasNext", bool(next_cursor))
    if not isinstance(has_next, bool):
        raise _invalid("Campo pageInfo.hasNext possui tipo invalido.")
    count = _optional_int(data, "count", default=fallback_count)
    return MlbbPageInfo(
        next_cursor=next_cursor,
        has_next=has_next and next_cursor is not None,
        count=fallback_count if count is None else count,
    )


def _required_mapping(
    data: Mapping[str, Any],
    field_name: str,
) -> Mapping[str, Any]:
    if field_name not in data:
        raise _invalid(f"Campo obrigatorio ausente: {field_name}.")
    return _mapping_value(data[field_name], field_name)


def _mapping_value(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _invalid(f"Campo {field_name} possui tipo invalido.")
    return value


def _required_sequence(
    data: Mapping[str, Any],
    field_name: str,
) -> Sequence[object]:
    if field_name not in data:
        raise _invalid(f"Campo obrigatorio ausente: data.{field_name}.")
    return _sequence_value(data[field_name], field_name)


def _sequence_value(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _invalid(f"Campo {field_name} possui tipo invalido.")
    return value


def _required_string(data: Mapping[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"Campo obrigatorio ausente ou invalido: {field_name}.")
    return value.strip()


def _optional_string(data: Mapping[str, Any], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise _invalid(f"Campo {field_name} possui tipo invalido.")
    return value


def _required_int(data: Mapping[str, Any], field_name: str) -> int:
    value = data.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _invalid(f"Campo obrigatorio ausente ou invalido: {field_name}.")
    return value


def _optional_int(
    data: Mapping[str, Any],
    field_name: str,
    *,
    default: int | None = None,
) -> int | None:
    value = data.get(field_name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(f"Campo {field_name} possui tipo invalido.")
    return value


def _optional_number(data: Mapping[str, Any], field_name: str) -> float | None:
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(f"Campo {field_name} possui tipo invalido.")
    return float(value)


def _optional_flag(data: Mapping[str, Any], field_name: str) -> bool | None:
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if not isinstance(value, int) or value not in {0, 1}:
        raise _invalid(f"Campo {field_name} possui flag invalida.")
    return bool(value)


def _int_tuple(
    value: object,
    *,
    field_name: str,
    default: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    if value is None and default is not None:
        return default
    values = _sequence_value(value, field_name)
    result: list[int] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, int):
            raise _invalid(f"Campo {field_name} possui item invalido.")
        result.append(item)
    return tuple(result)


def _required_battle_id(data: Mapping[str, Any]) -> str:
    if data.get("bid_s") not in {None, ""}:
        return _battle_id_value(data["bid_s"], field_name="bid_s")
    if "bid" not in data:
        raise _invalid("Campo obrigatorio ausente: bid_s ou bid.")
    return _battle_id_value(data["bid"], field_name="bid")


def _optional_battle_id(data: Mapping[str, Any]) -> str | None:
    if data.get("bid_s") not in {None, ""}:
        return _battle_id_value(data["bid_s"], field_name="bid_s")
    if data.get("bid") is None:
        return None
    return _battle_id_value(data["bid"], field_name="bid")


def _battle_id_value(value: object, *, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise _invalid(f"Campo {field_name} possui tipo invalido.")
    normalized = str(value).strip()
    if not normalized.isdigit() or int(normalized) <= 0:
        raise _invalid(f"Campo {field_name} possui valor invalido.")
    return normalized


def _optional_cursor(value: object, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise _invalid(f"Campo {field_name} possui tipo invalido.")
    return str(value)


def _invalid(message: str) -> MlbbInvalidResponseError:
    return MlbbInvalidResponseError(message)
