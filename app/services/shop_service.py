from __future__ import annotations

from app.models.shop import (
    RewardItem,
    RewardItemCreate,
    RewardPurchase,
    RewardType,
    ShopPurchaseResult,
    StockMode,
)
from app.repositories.economy_repository import SQLiteEconomyRepository


class ShopServiceError(Exception):
    """Erro base da loja."""


class ShopValidationError(ShopServiceError):
    """Erro de validacao da loja."""


class ShopService:
    """Regras de recompensas e compras."""

    def __init__(self, repository: SQLiteEconomyRepository) -> None:
        self._repository = repository

    async def create_reward(
        self,
        *,
        guild_id: int,
        name: str,
        description: str,
        reward_type: RewardType,
        price: int,
        stock_quantity: int | None,
        stock_mode: StockMode,
        max_per_user: int | None,
        role_id: int | None,
        delivery_message: str | None,
        created_by: int,
    ) -> RewardItem:
        name = self._require_text(name, "O nome da recompensa nao pode ficar vazio.")
        description = self._require_text(
            description,
            "A descricao da recompensa nao pode ficar vazia.",
        )
        if price <= 0:
            raise ShopValidationError("O preco precisa ser maior que zero.")
        if stock_quantity is not None and stock_quantity < 0:
            raise ShopValidationError("O estoque nao pode ser negativo.")
        if stock_mode is StockMode.LIMITED and stock_quantity is None:
            raise ShopValidationError("Recompensa limitada precisa de estoque.")
        if max_per_user is not None and max_per_user <= 0:
            raise ShopValidationError("O limite por usuario precisa ser positivo.")
        if reward_type is RewardType.ROLE and role_id is None:
            raise ShopValidationError("Recompensas de cargo precisam de um cargo.")

        reward = await self._repository.create_reward(
            RewardItemCreate(
                guild_id=guild_id,
                name=name[:100],
                description=description[:1000],
                type=reward_type,
                price=price,
                stock_quantity=stock_quantity,
                stock_mode=stock_mode,
                max_per_user=max_per_user,
                role_id=role_id,
                delivery_message=delivery_message[:1000] if delivery_message else None,
                created_by=created_by,
            )
        )
        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=created_by,
            action="REWARD_CREATE",
            target_resource_id=str(reward.id),
            after_data={
                "name": reward.name,
                "price": reward.price,
                "type": reward.type.value,
            },
            reason="reward_create",
        )
        return reward

    async def list_rewards(
        self,
        guild_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[RewardItem]:
        return await self._repository.list_rewards(
            guild_id,
            include_inactive=include_inactive,
        )

    async def get_reward(self, reward_id: int) -> RewardItem | None:
        return await self._repository.get_reward(reward_id)

    async def purchase_reward(
        self,
        *,
        guild_id: int,
        user_id: int,
        reward_id: int,
    ) -> ShopPurchaseResult:
        return await self._repository.purchase_reward(
            guild_id=guild_id,
            user_id=user_id,
            reward_id=reward_id,
        )

    async def list_purchases(
        self,
        guild_id: int,
        user_id: int,
        *,
        limit: int = 10,
    ) -> list[RewardPurchase]:
        return await self._repository.list_purchases(guild_id, user_id, limit=limit)

    @staticmethod
    def _require_text(value: str, message: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ShopValidationError(message)
        return normalized
