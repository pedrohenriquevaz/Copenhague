from __future__ import annotations

import pytest

from app.models.economy import EconomicTier
from app.services.economic_tier_service import (
    EconomicTierConfigurationError,
    EconomicTierService,
)


@pytest.mark.parametrize(
    ("balance", "identifier"),
    [
        (-1, "initial"),
        (0, "initial"),
        (5_000, "initial"),
        (5_001, "emerging"),
        (25_000, "emerging"),
        (25_001, "prosperous"),
        (99_999, "prosperous"),
        (100_000, "tycoon"),
        (350_000, "tycoon"),
        (350_001, "millionaire"),
        (10**30, "millionaire"),
    ],
)
def test_classify_economic_tier_at_every_boundary(
    balance: int,
    identifier: str,
) -> None:
    assert EconomicTierService().classify(balance).identifier == identifier


def test_classification_returns_complete_tier_value_object() -> None:
    tier = EconomicTierService().classify(100_000)

    assert tier == EconomicTier(
        identifier="tycoon",
        name="Magnata",
        minimum_balance=100_000,
        maximum_balance=350_000,
        level=4,
    )


def test_negative_balance_does_not_change_initial_tier_limits() -> None:
    tier = EconomicTierService().classify(-500)

    assert tier.identifier == "initial"
    assert tier.minimum_balance == 0


@pytest.mark.parametrize("balance", [True, 1.5, "5000", None])
def test_classification_rejects_non_integer_balances(balance: object) -> None:
    with pytest.raises(TypeError, match="inteiro"):
        EconomicTierService().classify(balance)  # type: ignore[arg-type]


def test_configuration_rejects_gaps_between_tiers() -> None:
    tiers = (
        EconomicTier("first", "Primeira", 0, 10, 1),
        EconomicTier("last", "Final", 12, None, 2),
    )

    with pytest.raises(EconomicTierConfigurationError, match="continuas"):
        EconomicTierService(tiers)


def test_configuration_rejects_overlaps_between_tiers() -> None:
    tiers = (
        EconomicTier("first", "Primeira", 0, 10, 1),
        EconomicTier("last", "Final", 10, None, 2),
    )

    with pytest.raises(EconomicTierConfigurationError, match="continuas"):
        EconomicTierService(tiers)
