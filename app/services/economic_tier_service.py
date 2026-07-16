from __future__ import annotations

from collections.abc import Sequence

from app.core.constants import ECONOMIC_TIERS
from app.models.economy import EconomicTier


class EconomicTierConfigurationError(ValueError):
    """Indica uma configuracao invalida de faixas economicas."""


class EconomicTierService:
    """Classifica o saldo oficial da carteira em uma faixa economica."""

    def __init__(self, tiers: Sequence[EconomicTier] = ECONOMIC_TIERS) -> None:
        self._tiers = tuple(tiers)
        self._validate_tiers(self._tiers)

    @property
    def tiers(self) -> tuple[EconomicTier, ...]:
        """Retorna a configuracao validada na ordem de nivel."""
        return self._tiers

    def classify(self, balance: int) -> EconomicTier:
        """Retorna a faixa do saldo; negativos sao classificados como iniciais."""
        if isinstance(balance, bool) or not isinstance(balance, int):
            raise TypeError("O saldo precisa ser um numero inteiro.")

        normalized_balance = max(0, balance)
        for tier in self._tiers:
            if tier.contains(normalized_balance):
                return tier
        raise EconomicTierConfigurationError("Nenhuma faixa cobre o saldo informado.")

    @staticmethod
    def _validate_tiers(tiers: tuple[EconomicTier, ...]) -> None:
        if not tiers:
            raise EconomicTierConfigurationError("Defina ao menos uma faixa economica.")
        if tiers[0].minimum_balance != 0:
            raise EconomicTierConfigurationError(
                "A primeira faixa deve comecar em zero."
            )

        identifiers: set[str] = set()
        for index, tier in enumerate(tiers):
            if not tier.identifier or not tier.name:
                raise EconomicTierConfigurationError(
                    "Identificador e nome da faixa sao obrigatorios."
                )
            if tier.identifier in identifiers:
                raise EconomicTierConfigurationError(
                    f"Identificador de faixa duplicado: {tier.identifier}."
                )
            identifiers.add(tier.identifier)
            if tier.level != index + 1:
                raise EconomicTierConfigurationError(
                    "Os niveis das faixas devem ser sequenciais a partir de um."
                )
            if tier.maximum_balance is None:
                if index != len(tiers) - 1:
                    raise EconomicTierConfigurationError(
                        "Somente a ultima faixa pode nao ter limite superior."
                    )
                continue
            if tier.maximum_balance < tier.minimum_balance:
                raise EconomicTierConfigurationError(
                    f"Limites invertidos na faixa {tier.identifier}."
                )
            if index + 1 < len(tiers):
                next_tier = tiers[index + 1]
                if next_tier.minimum_balance != tier.maximum_balance + 1:
                    raise EconomicTierConfigurationError(
                        "As faixas devem ser continuas, sem lacunas ou sobreposicoes."
                    )

        if tiers[-1].maximum_balance is not None:
            raise EconomicTierConfigurationError(
                "A ultima faixa deve aceitar saldos sem limite superior."
            )
