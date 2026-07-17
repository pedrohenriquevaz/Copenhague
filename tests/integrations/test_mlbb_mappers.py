from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.integrations.mlbb.errors import MlbbInvalidResponseError
from app.integrations.mlbb.mappers import (
    map_frequent_heroes,
    map_login,
    map_match_details,
    map_match_page,
    map_player_profile,
    map_player_stats,
    map_seasons,
)
from app.integrations.mlbb.rank_resolver import resolve_rank_name

FIXTURES = Path(__file__).parents[1] / "fixtures" / "mlbb"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_map_login_normalizes_and_hides_jwt_from_repr() -> None:
    result = map_login(load_fixture("login_success.json"))

    assert result.role_id == 123456789
    assert result.zone_id == 1234
    assert result.authenticated_at == 1700000000
    assert result.jwt == "fixture.jwt.never-real"
    assert "fixture.jwt.never-real" not in repr(result)
    assert not hasattr(result, "token")


def test_map_player_profile_ignores_extra_fields() -> None:
    profile = map_player_profile(load_fixture("user_info_success.json"))

    assert profile.name == "Jogador Ficticio"
    assert profile.current_rank_code == 8000
    assert profile.highest_rank_code == 9999
    assert profile.country_code == "BR"


def test_map_player_profile_tolerates_missing_optional_fields() -> None:
    profile = map_player_profile(load_fixture("user_info_incomplete.json"))

    assert profile.avatar_url is None
    assert profile.level is None
    assert profile.current_rank_code is None
    assert profile.country_code is None


def test_map_player_stats_normalizes_abbreviated_fields() -> None:
    stats = map_player_stats(load_fixture("user_stats_success.json"))

    assert stats.wins == 18
    assert stats.matches == 30
    assert stats.average_score_raw == 762.5
    assert stats.mvp_count == 7
    assert stats.season_ids == (40, 39)
    assert stats.highlights[0].battle_id == "9007199254740993"
    assert stats.highlights[0].hero.name == "Heroina Ficticia"


def test_map_seasons_returns_immutable_ids() -> None:
    seasons = map_seasons(load_fixture("seasons_success.json"))

    assert seasons == (40, 39, 38)


def test_map_match_page_prefers_precise_string_battle_id() -> None:
    page = map_match_page(load_fixture("matches_success.json"))

    assert page.matches[0].battle_id == "9007199254740993"
    assert page.matches[0].is_mvp is True
    assert page.matches[0].won is True
    assert page.page_info.next_cursor == "9007199254740995"
    assert page.page_info.has_next is True


def test_map_match_details_normalizes_participants_and_items() -> None:
    details = map_match_details(
        load_fixture("match_details_success.json"),
        season_id=40,
        match_id="9007199254740993",
    )

    participant = details.participants[0]
    assert details.battle_id == "9007199254740993"
    assert participant.player_name == "Jogador Ficticio"
    assert participant.item_ids == (2305, 3002, 0)
    assert participant.items[0].name == "Item Ficticio"
    assert participant.won is True


def test_map_frequent_heroes_normalizes_counts() -> None:
    page = map_frequent_heroes(load_fixture("frequent_heroes_success.json"))

    assert page.heroes[0].matches == 8
    assert page.heroes[0].wins == 7
    assert page.heroes[0].power_score == 1460
    assert page.page_info.has_next is False


def test_map_frequent_heroes_tolerates_optional_fields_and_page_info() -> None:
    page = map_frequent_heroes({"code": 0, "data": {"result": [{"hid": 17}]}})

    assert page.heroes[0].matches == 0
    assert page.heroes[0].hero.hero_id == 17
    assert page.page_info.count == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"code": 0},
        {"code": 0, "data": {"roleid": 1, "zoneid": 2}},
    ],
)
def test_map_login_rejects_missing_required_field(payload: dict[str, Any]) -> None:
    with pytest.raises(MlbbInvalidResponseError):
        map_login(payload)


def test_map_match_rejects_missing_battle_id() -> None:
    with pytest.raises(MlbbInvalidResponseError, match="bid_s ou bid"):
        map_match_page({"code": 0, "data": {"result": [{}]}})


def test_rank_resolver_uses_only_documented_fallback() -> None:
    assert resolve_rank_name(8000) == "Rank não mapeado (código 8000)"
    assert resolve_rank_name(None) == "Não disponível"
