from __future__ import annotations

from app.models.shop import (
    LevelConfig,
    LevelUpgradePurchase,
    LevelUpgradeResult,
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
        duration_days: int | None = None,
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
        duration_days = self._normalize_duration_days(duration_days)

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
                duration_days=duration_days,
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
                "duration_days": reward.duration_days,
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

    async def update_reward(
        self,
        *,
        guild_id: int,
        reward_id: int,
        actor_id: int,
        name: str | None = None,
        description: str | None = None,
        reward_type: RewardType | None = None,
        price: int | None = None,
        stock_quantity: int | None = None,
        stock_mode: StockMode | None = None,
        max_per_user: int | None = None,
        role_id: int | None = None,
        delivery_message: str | None = None,
        is_active: bool | None = None,
        duration_days: int | None = None,
    ) -> RewardItem:
        before = await self._repository.get_reward(reward_id)
        if before is None or before.guild_id != guild_id or before.deleted_at:
            raise ShopValidationError("Recompensa nao encontrada.")

        updates: dict[str, object] = {}
        if name is not None:
            updates["name"] = self._require_text(
                name,
                "O nome da recompensa nao pode ficar vazio.",
            )[:100]
        if description is not None:
            updates["description"] = self._require_text(
                description,
                "A descricao da recompensa nao pode ficar vazia.",
            )[:1000]
        if reward_type is not None:
            updates["type"] = reward_type.value
        if price is not None:
            if price <= 0:
                raise ShopValidationError("O preco precisa ser maior que zero.")
            updates["price"] = price

        if stock_mode is StockMode.UNLIMITED:
            updates["stock_mode"] = StockMode.UNLIMITED.value
            updates["stock_quantity"] = None
        elif stock_mode is StockMode.LIMITED:
            if stock_quantity is None:
                stock_quantity = before.stock_quantity
            if stock_quantity is None:
                raise ShopValidationError(
                    "Informe o estoque para usar estoque limitado."
                )
            if stock_quantity < 0:
                raise ShopValidationError("O estoque nao pode ser negativo.")
            updates["stock_mode"] = StockMode.LIMITED.value
            updates["stock_quantity"] = stock_quantity
        elif stock_quantity is not None:
            if stock_quantity < 0:
                raise ShopValidationError("O estoque nao pode ser negativo.")
            updates["stock_mode"] = StockMode.LIMITED.value
            updates["stock_quantity"] = stock_quantity

        if max_per_user is not None:
            if max_per_user < 0:
                raise ShopValidationError("O limite por usuario nao pode ser negativo.")
            updates["max_per_user"] = max_per_user or None
        if role_id is not None:
            updates["role_id"] = role_id
        if delivery_message is not None:
            normalized_delivery = delivery_message.strip()
            updates["delivery_message"] = (
                normalized_delivery[:1000] if normalized_delivery else None
            )
        if duration_days is not None:
            updates["duration_days"] = self._normalize_duration_days(duration_days)
        if is_active is not None:
            updates["is_active"] = int(is_active)

        target_type = reward_type or before.type
        target_role_id = role_id if role_id is not None else before.role_id
        if target_type is RewardType.ROLE and target_role_id is None:
            raise ShopValidationError("Recompensas de cargo precisam de um cargo.")
        if not updates:
            raise ShopValidationError("Informe ao menos um campo para atualizar.")

        updated = await self._repository.update_reward(
            guild_id=guild_id,
            reward_id=reward_id,
            updates=updates,
        )
        if updated is None:
            raise ShopValidationError("Recompensa nao encontrada.")

        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="REWARD_UPDATE",
            target_resource_id=str(reward_id),
            before_data=self._reward_audit_data(before),
            after_data=self._reward_audit_data(updated),
            reason="reward_update",
        )
        return updated

    async def remove_reward(
        self,
        *,
        guild_id: int,
        reward_id: int,
        actor_id: int,
        reason: str | None = None,
    ) -> RewardItem:
        before = await self._repository.get_reward(reward_id)
        if before is None or before.guild_id != guild_id or before.deleted_at:
            raise ShopValidationError("Recompensa nao encontrada.")

        removed = await self._repository.remove_reward(
            guild_id=guild_id,
            reward_id=reward_id,
        )
        if removed is None:
            raise ShopValidationError("Recompensa nao encontrada.")

        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="REWARD_REMOVE",
            target_resource_id=str(reward_id),
            before_data=self._reward_audit_data(before),
            after_data=self._reward_audit_data(removed),
            reason=reason or "reward_remove",
        )
        return removed

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

    async def configure_level(
        self,
        *,
        guild_id: int,
        level: int,
        role_id: int,
        price: int,
        is_active: bool,
        actor_id: int,
        saves_reward: int = 0,
    ) -> LevelConfig:
        if level <= 0:
            raise ShopValidationError("O nível precisa ser maior que zero.")
        if price <= 0:
            raise ShopValidationError("O custo do nível precisa ser maior que zero.")
        if role_id <= 0:
            raise ShopValidationError("Informe um cargo válido para o nível.")

        if saves_reward < 0:
            raise ShopValidationError("A quantidade de saves não pode ser negativa.")

        config = await self._repository.upsert_level_config(
            guild_id=guild_id,
            level=level,
            role_id=role_id,
            price=price,
            is_active=is_active,
            created_by=actor_id,
            saves_reward=saves_reward,
        )
        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="LEVEL_CONFIG_UPSERT",
            target_resource_id=str(level),
            after_data=self._level_audit_data(config),
            reason="level_config",
        )
        return config

    async def list_levels(
        self,
        guild_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[LevelConfig]:
        return await self._repository.list_level_configs(
            guild_id,
            include_inactive=include_inactive,
        )

    async def list_user_level_upgrades(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[LevelUpgradePurchase]:
        return await self._repository.list_user_level_upgrades(guild_id, user_id)

    async def get_next_level(
        self,
        *,
        guild_id: int,
        user_id: int,
        current_role_ids: set[int] | None = None,
    ) -> tuple[int, LevelConfig | None, list[LevelConfig]]:
        levels = await self.list_levels(guild_id)
        if not levels:
            return 0, None, []

        purchases = await self.list_user_level_upgrades(guild_id, user_id)
        purchased_level = max((purchase.level for purchase in purchases), default=0)
        role_level = 0
        if current_role_ids:
            role_level = max(
                (
                    config.level
                    for config in levels
                    if config.role_id in current_role_ids
                ),
                default=0,
            )
        current_level = max(purchased_level, role_level)
        next_level = next(
            (config for config in levels if config.level > current_level),
            None,
        )
        return current_level, next_level, levels

    async def purchase_level_upgrade(
        self,
        *,
        guild_id: int,
        user_id: int,
        level: int,
    ) -> LevelUpgradeResult:
        return await self._repository.purchase_level_upgrade(
            guild_id=guild_id,
            user_id=user_id,
            level=level,
        )

    @staticmethod
    def _require_text(value: str, message: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ShopValidationError(message)
        return normalized

    @staticmethod
    def _reward_audit_data(reward: RewardItem) -> dict[str, object]:
        return {
            "id": reward.id,
            "name": reward.name,
            "description": reward.description,
            "type": reward.type.value,
            "price": reward.price,
            "stock_quantity": reward.stock_quantity,
            "stock_mode": reward.stock_mode.value,
            "max_per_user": reward.max_per_user,
            "role_id": reward.role_id,
            "delivery_message": reward.delivery_message,
            "duration_days": reward.duration_days,
            "is_active": reward.is_active,
            "deleted_at": reward.deleted_at.isoformat() if reward.deleted_at else None,
        }

    @staticmethod
    def _level_audit_data(level: LevelConfig) -> dict[str, object]:
        return {
            "guild_id": level.guild_id,
            "level": level.level,
            "role_id": level.role_id,
            "price": level.price,
            "saves_reward": level.saves_reward,
            "is_active": level.is_active,
        }

    @staticmethod
    def _normalize_duration_days(value: int | None) -> int | None:
        if value is None or value == 0:
            return None
        if value < 0:
            raise ShopValidationError("A duração em dias não pode ser negativa.")
        if value > 3650:
            raise ShopValidationError("A duração máxima é de 3650 dias.")
        return value
