"""Constantes compartilhadas do projeto."""

from app.models.economy import EconomicTier

# Configuracao unica das faixas economicas. Como o saldo oficial e inteiro, os
# limites inferior e superior sao inclusivos. ``None`` representa uma faixa sem
# limite superior.
ECONOMIC_TIERS: tuple[EconomicTier, ...] = (
    EconomicTier("initial", "Inicial", 0, 5_000, 1),
    EconomicTier("emerging", "Emergente", 5_001, 25_000, 2),
    EconomicTier("prosperous", "Próspero", 25_001, 99_999, 3),
    EconomicTier("tycoon", "Magnata", 100_000, 350_000, 4),
    EconomicTier("millionaire", "Milionário", 350_001, None, 5),
)
