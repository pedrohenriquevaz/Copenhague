from __future__ import annotations

import pytest

from app.integrations.mlbb.dto import MlbbStatHighlightKind
from app.integrations.mlbb.rank_resolver import resolve_rank_name
from app.utils.mlbb_formatters import (
    NOT_AVAILABLE,
    calculate_win_rate,
    format_decimal_pt_br,
    format_duration_hours,
    format_highlight_value,
    format_optional_number,
    format_percentage,
    format_score,
    highlight_label,
    mask_game_id,
    normalize_score,
)


def test_calculate_win_rate_rounds_and_is_zero_safe() -> None:
    assert calculate_win_rate(2, 3) == 66.67
    assert calculate_win_rate(0, 0) == 0.0
    assert calculate_win_rate(4, -1) == 0.0


def test_score_is_normalized_from_hundredths() -> None:
    assert normalize_score(762.5) == 7.62
    assert normalize_score(0) == 0.0
    assert normalize_score(None) is None
    assert format_score(1180) == "11,80"
    assert format_score(None) == NOT_AVAILABLE


def test_numbers_and_percentage_are_formatted_for_pt_br() -> None:
    assert format_decimal_pt_br(1234.5) == "1.234,50"
    assert format_optional_number(1234) == "1.234"
    assert format_optional_number(12.5) == "12,50"
    assert format_optional_number(0) == "0"
    assert format_optional_number(None) == NOT_AVAILABLE
    assert format_percentage(66.67) == "66,67%"
    assert format_percentage(None) == NOT_AVAILABLE


def test_negative_decimal_places_is_rejected() -> None:
    with pytest.raises(ValueError, match="não pode ser negativo"):
        format_decimal_pt_br(1, decimal_places=-1)


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        (12.25, "12h 15min"),
        (1, "1h"),
        (0.5, "30min"),
        (0, "0min"),
        (None, NOT_AVAILABLE),
        (-1, NOT_AVAILABLE),
    ],
)
def test_duration_is_formatted_as_hours_and_minutes(
    hours: float | None,
    expected: str,
) -> None:
    assert format_duration_hours(hours) == expected


def test_game_id_is_masked_and_area_is_preserved() -> None:
    assert mask_game_id(12345678, 1234) == "••••5678 (Área ••34)"
    assert mask_game_id("12345678") == "••••5678"
    assert mask_game_id(1234) == "•234"
    assert mask_game_id(None, 1234) == NOT_AVAILABLE


def test_invalid_mask_options_are_rejected() -> None:
    with pytest.raises(ValueError, match="não pode ser negativo"):
        mask_game_id(12345678, visible_digits=-1)


@pytest.mark.parametrize("kind", list(MlbbStatHighlightKind))
def test_every_highlight_kind_has_a_safe_label(kind: MlbbStatHighlightKind) -> None:
    assert highlight_label(kind) != "Destaque"


def test_only_highest_score_highlight_is_normalized() -> None:
    assert format_highlight_value(MlbbStatHighlightKind.HIGHEST_SCORE, 1180) == "11,80"
    assert format_highlight_value(MlbbStatHighlightKind.HIGHEST_KILLS, 1180) == "1.180"
    assert (
        format_highlight_value(MlbbStatHighlightKind.MOST_DAMAGE, None) == NOT_AVAILABLE
    )


def test_rank_resolver_uses_only_documented_fallbacks() -> None:
    assert resolve_rank_name(None) == NOT_AVAILABLE
    assert resolve_rank_name(9999) == "Rank não mapeado (código 9999)"
