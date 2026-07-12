from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class RewardType(StrEnum):
    """Tipos de recompensa da loja."""

    ROLE = "ROLE"
    CUSTOM_TEXT = "CUSTOM_TEXT"
    MANUAL_REWARD = "MANUAL_REWARD"
    DIGITAL_CODE = "DIGITAL_CODE"
    VIP_ACCESS = "VIP_ACCESS"
    EVENT_ENTRY = "EVENT_ENTRY"


class StockMode(StrEnum):
    """Modo de estoque de uma recompensa."""

    LIMITED = "LIMITED"
    UNLIMITED = "UNLIMITED"


class PurchaseStatus(StrEnum):
    """Estado geral de uma compra."""

    COMPLETED = "COMPLETED"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"


class DeliveryStatus(StrEnum):
    """Estado de entrega de uma recompensa."""

    DELIVERED = "DELIVERED"
    PENDING = "PENDING"
    FAILED = "FAILED"


class ShopPurchaseStatus(StrEnum):
    """Resultado de uma tentativa de compra."""

    SUCCESS = "SUCCESS"
    REWARD_NOT_FOUND = "REWARD_NOT_FOUND"
    REWARD_INACTIVE = "REWARD_INACTIVE"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    LIMIT_REACHED = "LIMIT_REACHED"


class LevelUpgradeStatus(StrEnum):
    """Resultado de uma tentativa de subir de nivel."""

    SUCCESS = "SUCCESS"
    LEVEL_NOT_FOUND = "LEVEL_NOT_FOUND"
    LEVEL_INACTIVE = "LEVEL_INACTIVE"
    ALREADY_OWNED = "ALREADY_OWNED"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"


@dataclass(slots=True)
class RewardItemCreate:
    """Dados para criar uma recompensa."""

    guild_id: int
    name: str
    description: str
    type: RewardType
    price: int
    stock_quantity: int | None
    stock_mode: StockMode
    max_per_user: int | None
    role_id: int | None
    delivery_message: str | None
    created_by: int
    duration_days: int | None = None


@dataclass(slots=True)
class RewardItem:
    """Recompensa compravel na loja."""

    id: int
    guild_id: int
    name: str
    description: str
    type: RewardType
    price: int
    stock_quantity: int | None
    stock_mode: StockMode
    max_per_user: int | None
    role_id: int | None
    delivery_message: str | None
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    duration_days: int | None = None


@dataclass(slots=True)
class RewardPurchase:
    """Compra de recompensa feita por um usuario."""

    id: int
    guild_id: int
    user_id: int
    reward_id: int
    transaction_id: int | None
    price_paid: int
    status: PurchaseStatus
    delivery_status: DeliveryStatus
    metadata: dict[str, Any]
    created_at: datetime
    delivered_at: datetime | None


@dataclass(slots=True)
class ShopPurchaseResult:
    """Resultado completo de uma compra."""

    status: ShopPurchaseStatus
    reward: RewardItem | None = None
    purchase: RewardPurchase | None = None
    balance_before: int = 0
    balance_after: int = 0
    missing_points: int = 0


@dataclass(slots=True)
class LevelConfig:
    """Nivel progressivo configurado para compra na loja."""

    guild_id: int
    level: int
    role_id: int
    price: int
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime
    saves_reward: int = 0


@dataclass(slots=True)
class LevelUpgradePurchase:
    """Compra imutavel de um nivel progressivo."""

    id: int
    guild_id: int
    user_id: int
    level: int
    role_id: int
    transaction_id: int
    price_paid: int
    created_at: datetime


@dataclass(slots=True)
class LevelUpgradeResult:
    """Resultado completo da compra de upgrade de nivel."""

    status: LevelUpgradeStatus
    level_config: LevelConfig | None = None
    purchase: LevelUpgradePurchase | None = None
    balance_before: int = 0
    balance_after: int = 0
    missing_points: int = 0
