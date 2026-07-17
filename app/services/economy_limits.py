from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from app.models.economy import (
    CasinoPayoutSettlementResult,
    EconomicTier,
    EconomyTransactionType,
)
from app.models.giveaway import utc_now
from app.models.guild_settings import GuildEconomySettings
from app.repositories.economy_protocol import EconomyRepositoryProtocol
from app.services.economic_tier_service import EconomicTierService

DAILY_PROFIT_TIMEZONE = timezone(timedelta(hours=-3))
DAILY_PROFIT_TIMEZONE_OFFSET_MINUTES = -180
PROFIT_DIFFICULTY_ROLL_MAX = 10_000
ECONOMIC_DIFFICULTY_THRESHOLD_BPS = 7_000
SEVERE_ECONOMIC_DIFFICULTY_THRESHOLD_BPS = 9_000
ECONOMIC_LIMITER_EXEMPT_MAX_LEVEL = 2
ECONOMIC_POLICY_SNAPSHOT_VERSION = 1

logger = logging.getLogger(__name__)


class EconomicDifficultyPolicyName(StrEnum):
    DISABLED = "disabled"
    EXEMPT = "tier_exempt"
    INVALID_LIMIT = "invalid_limit"
    STANDARD = "standard"
    INCREASED = "increased"
    SEVERE = "severe"


@dataclass(frozen=True, slots=True)
class EconomicDifficultyStep:
    threshold_bps: int
    difficulty_bps: int
    policy: EconomicDifficultyPolicyName


# Fonte unica para limiares, nomes e dificuldade. Ordem decrescente.
DAILY_PROFIT_DIFFICULTY_STEPS: tuple[EconomicDifficultyStep, ...] = (
    EconomicDifficultyStep(
        SEVERE_ECONOMIC_DIFFICULTY_THRESHOLD_BPS,
        5_000,
        EconomicDifficultyPolicyName.SEVERE,
    ),
    EconomicDifficultyStep(
        ECONOMIC_DIFFICULTY_THRESHOLD_BPS,
        3_500,
        EconomicDifficultyPolicyName.INCREASED,
    ),
)


@dataclass(frozen=True, slots=True)
class EconomicDifficultyDecision:
    """Decisao imutavel que permanece estavel durante uma rodada."""

    tier: EconomicTier | None
    daily_profit: int
    daily_limit: int
    profit_ratio_bps: int
    difficulty_bps: int
    policy: EconomicDifficultyPolicyName
    window_start: datetime
    daily_profit_evaluated: bool = True

    @property
    def limiters_apply(self) -> bool:
        """Compatibilidade: indica se o teto de lucro pode ser aplicado."""
        return self.profit_cap_applies

    @property
    def profit_cap_applies(self) -> bool:
        return self.policy not in {
            EconomicDifficultyPolicyName.DISABLED,
            EconomicDifficultyPolicyName.EXEMPT,
            EconomicDifficultyPolicyName.INVALID_LIMIT,
        }

    @property
    def purchase_limit_applies(self) -> bool:
        return self.policy not in {
            EconomicDifficultyPolicyName.DISABLED,
            EconomicDifficultyPolicyName.EXEMPT,
        }


class EconomicDifficultyPolicyService:
    """Servico de dominio reutilizavel para selecionar politicas economicas."""

    def __init__(
        self,
        repository: EconomyRepositoryProtocol,
        tier_service: EconomicTierService,
        *,
        increased_threshold_bps: int = ECONOMIC_DIFFICULTY_THRESHOLD_BPS,
    ) -> None:
        self._repository = repository
        self._tier_service = tier_service
        if not 1 <= increased_threshold_bps < SEVERE_ECONOMIC_DIFFICULTY_THRESHOLD_BPS:
            raise ValueError("O limiar de dificuldade deve ficar entre 1 e 8999 bps.")
        default_increased = DAILY_PROFIT_DIFFICULTY_STEPS[1]
        self._difficulty_steps = (
            DAILY_PROFIT_DIFFICULTY_STEPS[0],
            EconomicDifficultyStep(
                increased_threshold_bps,
                default_increased.difficulty_bps,
                default_increased.policy,
            ),
        )

    async def select(
        self,
        settings: GuildEconomySettings,
        *,
        guild_id: int,
        user_id: int,
        game: str,
    ) -> EconomicDifficultyDecision:
        return await select_economic_difficulty_policy(
            self._repository,
            settings,
            guild_id=guild_id,
            user_id=user_id,
            game=game,
            tier_service=self._tier_service,
            difficulty_steps=self._difficulty_steps,
        )

    @staticmethod
    def snapshot(decision: EconomicDifficultyDecision) -> dict[str, Any]:
        return serialize_economic_difficulty_decision(decision)

    @staticmethod
    def restore(snapshot: dict[str, Any]) -> EconomicDifficultyDecision:
        return deserialize_economic_difficulty_decision(snapshot)

    async def settle_payout(
        self,
        decision: EconomicDifficultyDecision,
        *,
        guild_id: int,
        user_id: int,
        stake: int,
        payout: int,
        transaction_type: EconomyTransactionType,
        reason: str,
        metadata: dict[str, object],
        idempotency_key: str | None = None,
    ) -> CasinoPayoutSettlementResult:
        cap = (
            decision.daily_limit
            if decision.profit_cap_applies and payout > stake
            else None
        )
        settlement_metadata = {
            **metadata,
            "economic_policy": decision.policy.value,
            "economic_tier": (
                decision.tier.identifier if decision.tier is not None else None
            ),
            "economic_ratio_bps": decision.profit_ratio_bps,
            "economic_daily_limit": decision.daily_limit,
            "economic_policy_window_start": decision.window_start.isoformat(),
        }
        result = await self._repository.settle_casino_payout(
            guild_id=guild_id,
            user_id=user_id,
            requested_payout=payout,
            transaction_type=transaction_type,
            reason=reason,
            metadata=settlement_metadata,
            daily_profit_limit=cap,
            profit_timezone_offset_minutes=DAILY_PROFIT_TIMEZONE_OFFSET_MINUTES,
            idempotency_key=idempotency_key,
        )
        logger.debug(
            "economic_payout_policy guild_id=%s user_id=%s tier=%s "
            "daily_profit=%s daily_limit=%s ratio_bps=%s policy=%s game=%s "
            "requested_payout=%s paid_payout=%s settlement_window_start=%s "
            "idempotent_replay=%s",
            guild_id,
            user_id,
            decision.tier.identifier if decision.tier else "not_evaluated",
            result.daily_profit_before if cap is not None else "not_evaluated",
            decision.daily_limit,
            decision.profit_ratio_bps,
            decision.policy.value,
            metadata.get("game", "unspecified"),
            result.requested_payout,
            result.paid_payout,
            result.profit_window_start.isoformat(),
            result.idempotent_replay,
        )
        return result

    async def select_for_settlement(
        self,
        settings: GuildEconomySettings,
        *,
        guild_id: int,
        user_id: int,
        game: str,
        stake: int,
    ) -> EconomicDifficultyDecision:
        """Reconstrói a faixa anterior ao débito em jogos sem snapshot persistido."""
        balance_override: int | None = None
        if settings.casino_limiters_enabled:
            wallet = await self._repository.get_wallet(guild_id, user_id)
            balance_override = wallet.balance + max(0, stake)
        return await select_economic_difficulty_policy(
            self._repository,
            settings,
            guild_id=guild_id,
            user_id=user_id,
            game=game,
            tier_service=self._tier_service,
            balance_override=balance_override,
            difficulty_steps=self._difficulty_steps,
        )

    async def decision_for_settlement(
        self,
        snapshot: dict[str, Any] | None,
        settings: GuildEconomySettings,
        *,
        guild_id: int,
        user_id: int,
        game: str,
        stake: int,
    ) -> EconomicDifficultyDecision:
        """Restaura a politica inicial; partidas legadas usam fallback explicito."""
        if snapshot is not None:
            return self.restore(snapshot)
        logger.warning(
            "economic_policy_snapshot_missing guild_id=%s user_id=%s game=%s",
            guild_id,
            user_id,
            game,
        )
        return await self.select_for_settlement(
            settings,
            guild_id=guild_id,
            user_id=user_id,
            game=game,
            stake=stake,
        )


def current_daily_profit_window_start(*, now: datetime | None = None) -> datetime:
    local_now = (now or utc_now()).astimezone(DAILY_PROFIT_TIMEZONE)
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0)


async def select_economic_difficulty_policy(
    repository: EconomyRepositoryProtocol,
    settings: GuildEconomySettings,
    *,
    guild_id: int,
    user_id: int,
    game: str,
    tier_service: EconomicTierService | None = None,
    balance_override: int | None = None,
    difficulty_steps: tuple[
        EconomicDifficultyStep, ...
    ] = DAILY_PROFIT_DIFFICULTY_STEPS,
) -> EconomicDifficultyDecision:
    """Seleciona e registra a politica antes do inicio de uma rodada."""
    window_start = current_daily_profit_window_start()
    daily_limit = settings.casino_daily_profit_limit

    if not settings.casino_limiters_enabled:
        return _decision(
            None,
            0,
            daily_limit,
            0,
            0,
            "disabled",
            window_start,
            guild_id,
            user_id,
            game,
            daily_profit_evaluated=False,
        )
    classifier = tier_service or EconomicTierService()
    balance = balance_override
    if balance is None:
        wallet = await repository.get_wallet(guild_id, user_id)
        balance = wallet.balance
    tier = classifier.classify(balance)
    if tier.level <= ECONOMIC_LIMITER_EXEMPT_MAX_LEVEL:
        return _decision(
            tier,
            0,
            daily_limit,
            0,
            0,
            "tier_exempt",
            window_start,
            guild_id,
            user_id,
            game,
            daily_profit_evaluated=False,
        )
    if daily_limit <= 0:
        return _decision(
            tier,
            0,
            daily_limit,
            0,
            0,
            "invalid_limit",
            window_start,
            guild_id,
            user_id,
            game,
            daily_profit_evaluated=False,
        )

    daily_profit = await repository.get_user_casino_profit_since(
        guild_id, user_id, window_start
    )
    ratio_bps = max(0, daily_profit) * PROFIT_DIFFICULTY_ROLL_MAX // daily_limit
    difficulty_bps = calculate_daily_profit_difficulty_bps(
        daily_profit,
        settings,
        tier_level=tier.level,
        difficulty_steps=difficulty_steps,
    )
    policy = EconomicDifficultyPolicyName.STANDARD
    for step in difficulty_steps:
        if ratio_bps >= step.threshold_bps:
            policy = step.policy
            break
    return _decision(
        tier,
        daily_profit,
        daily_limit,
        ratio_bps,
        difficulty_bps,
        policy,
        window_start,
        guild_id,
        user_id,
        game,
    )


def _decision(
    tier: EconomicTier | None,
    profit: int,
    limit: int,
    ratio_bps: int,
    difficulty_bps: int,
    policy: EconomicDifficultyPolicyName | str,
    window_start: datetime,
    guild_id: int,
    user_id: int,
    game: str,
    *,
    daily_profit_evaluated: bool = True,
) -> EconomicDifficultyDecision:
    selected = EconomicDifficultyPolicyName(policy)
    logger.debug(
        "economic_difficulty_policy guild_id=%s user_id=%s tier=%s daily_profit=%s "
        "daily_limit=%s ratio_bps=%s policy=%s game=%s",
        guild_id,
        user_id,
        tier.identifier if tier else "not_evaluated",
        profit if daily_profit_evaluated else "not_evaluated",
        limit,
        ratio_bps,
        selected.value,
        game,
    )
    return EconomicDifficultyDecision(
        tier,
        profit,
        limit,
        ratio_bps,
        difficulty_bps,
        selected,
        window_start,
        daily_profit_evaluated,
    )


def calculate_daily_profit_difficulty_bps(
    current_profit: int,
    settings: GuildEconomySettings,
    *,
    tier_level: int = 3,
    difficulty_steps: tuple[
        EconomicDifficultyStep, ...
    ] = DAILY_PROFIT_DIFFICULTY_STEPS,
) -> int:
    if (
        not settings.casino_limiters_enabled
        or settings.casino_daily_profit_limit <= 0
        or current_profit <= 0
        or tier_level <= ECONOMIC_LIMITER_EXEMPT_MAX_LEVEL
    ):
        return 0
    profit_ratio_bps = (
        current_profit * PROFIT_DIFFICULTY_ROLL_MAX
    ) // settings.casino_daily_profit_limit
    for step in difficulty_steps:
        if profit_ratio_bps >= step.threshold_bps:
            return step.difficulty_bps
    return 0


def apply_daily_profit_difficulty_to_probability(
    probability_bps: int,
    difficulty_bps: int,
) -> int:
    if probability_bps <= 0:
        return 0
    if difficulty_bps <= 0:
        return min(probability_bps, PROFIT_DIFFICULTY_ROLL_MAX)
    remaining_bps = max(0, PROFIT_DIFFICULTY_ROLL_MAX - difficulty_bps)
    adjusted = (probability_bps * remaining_bps) // PROFIT_DIFFICULTY_ROLL_MAX
    return max(1, min(adjusted, PROFIT_DIFFICULTY_ROLL_MAX))


async def apply_daily_casino_profit_cap(
    repository: EconomyRepositoryProtocol,
    settings: GuildEconomySettings,
    *,
    guild_id: int,
    user_id: int,
    stake: int,
    payout: int,
    game: str = "unspecified",
) -> int:
    if payout <= 0 or payout <= stake:
        return payout
    decision = await select_economic_difficulty_policy(
        repository, settings, guild_id=guild_id, user_id=user_id, game=game
    )
    if not decision.limiters_apply:
        return payout
    remaining_payout = decision.daily_limit - decision.daily_profit
    return max(0, min(payout, remaining_payout))


def serialize_economic_difficulty_decision(
    decision: EconomicDifficultyDecision,
) -> dict[str, Any]:
    tier = decision.tier
    return {
        "version": ECONOMIC_POLICY_SNAPSHOT_VERSION,
        "tier": (
            {
                "identifier": tier.identifier,
                "name": tier.name,
                "minimum_balance": tier.minimum_balance,
                "maximum_balance": tier.maximum_balance,
                "level": tier.level,
            }
            if tier is not None
            else None
        ),
        "daily_profit": decision.daily_profit,
        "daily_limit": decision.daily_limit,
        "profit_ratio_bps": decision.profit_ratio_bps,
        "difficulty_bps": decision.difficulty_bps,
        "policy": decision.policy.value,
        "window_start": decision.window_start.isoformat(),
        "daily_profit_evaluated": decision.daily_profit_evaluated,
    }


def deserialize_economic_difficulty_decision(
    snapshot: dict[str, Any],
) -> EconomicDifficultyDecision:
    if not isinstance(snapshot, dict):
        raise ValueError("O snapshot da politica economica precisa ser um objeto.")
    if snapshot.get("version") != ECONOMIC_POLICY_SNAPSHOT_VERSION:
        raise ValueError("Versao de snapshot da politica economica nao suportada.")
    tier_data = snapshot.get("tier")
    tier = None
    if tier_data is not None:
        if not isinstance(tier_data, dict):
            raise ValueError("A faixa do snapshot economico e invalida.")
        tier = EconomicTier(
            identifier=str(tier_data["identifier"]),
            name=str(tier_data["name"]),
            minimum_balance=_snapshot_int(tier_data, "minimum_balance"),
            maximum_balance=(
                _snapshot_int(tier_data, "maximum_balance")
                if tier_data.get("maximum_balance") is not None
                else None
            ),
            level=_snapshot_int(tier_data, "level"),
        )
    window_start = datetime.fromisoformat(str(snapshot["window_start"]))
    if window_start.tzinfo is None:
        raise ValueError("O snapshot economico precisa incluir timezone.")
    evaluated = snapshot["daily_profit_evaluated"]
    if not isinstance(evaluated, bool):
        raise ValueError(
            "O campo daily_profit_evaluated do snapshot economico e invalido."
        )
    return EconomicDifficultyDecision(
        tier=tier,
        daily_profit=_snapshot_int(snapshot, "daily_profit"),
        daily_limit=_snapshot_int(snapshot, "daily_limit"),
        profit_ratio_bps=_snapshot_int(snapshot, "profit_ratio_bps"),
        difficulty_bps=_snapshot_int(snapshot, "difficulty_bps"),
        policy=EconomicDifficultyPolicyName(str(snapshot["policy"])),
        window_start=window_start,
        daily_profit_evaluated=evaluated,
    )


def _snapshot_int(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"O campo {key} do snapshot economico e invalido.")
    return value
