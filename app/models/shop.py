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
