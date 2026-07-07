from __future__ import annotations

import random
from datetime import timedelta, timezone

from app.models.economy import (
    BalanceMutationResult,
    BotRewardClaimResult,
    EconomyTransaction,
    EconomyTransactionType,
    UserWallet,
)
from app.models.giveaway import utc_now
from app.repositories.economy_repository import SQLiteEconomyRepository


class EconomyServiceError(Exception):
    """Erro base da economia."""


class EconomyValidationError(EconomyServiceError):
    """Erro de validacao de entrada da economia."""


class EconomyService:
    """Regras de carteira, saldo, transacoes e ajustes administrativos."""

    DAILY_GIFT_KEY = "daily_gift"
    STARTER_PACK_KEY = "starter_pack"
    DAILY_GIFT_MIN = 50
    DAILY_GIFT_MAX = 200
    STARTER_PACK_AMOUNT = 1500
    DAILY_GIFT_TIMEZONE = timezone(timedelta(hours=-3))

    def __init__(self, repository: SQLiteEconomyRepository) -> None:
        self._repository = repository

    async def get_wallet(self, guild_id: int, user_id: int) -> UserWallet:
        return await self._repository.get_wallet(guild_id, user_id)

    async def list_history(
        self,
        guild_id: int,
        user_id: int,
        *,
        limit: int = 10,
    ) -> list[EconomyTransaction]:
        return await self._repository.list_transactions(guild_id, user_id, limit=limit)

    async def list_ranking(
        self,
        guild_id: int,
        *,
        limit: int = 10,
    ) -> list[UserWallet]:
        return await self._repository.list_top_wallets(guild_id, limit=limit)

    async def give_points(
        self,
        *,
        guild_id: int,
        user_id: int,
        actor_id: int,
        amount: int,
        reason: str,
    ) -> BalanceMutationResult:
        self._validate_positive_amount(amount)
        reason = self._require_reason(reason)
        settings = await self._repository.get_guild_settings(guild_id)
        if amount > settings.max_admin_grant_per_use:
            raise EconomyValidationError(
                f"A quantidade maxima por uso e {settings.max_admin_grant_per_use}."
            )

        result = await self._repository.mutate_balance(
            guild_id=guild_id,
            user_id=user_id,
            amount=amount,
            transaction_type=EconomyTransactionType.ADMIN_GIVE,
            actor_id=actor_id,
            reason=reason,
            metadata={"source": "admin_command"},
        )
        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action=EconomyTransactionType.ADMIN_GIVE.value,
            target_user_id=user_id,
            before_data={"balance": result.transaction.balance_before},
            after_data={"balance": result.transaction.balance_after, "amount": amount},
            reason=reason,
        )
        return result

    async def give_points_bulk(
        self,
        *,
        guild_id: int,
        user_ids: list[int],
        actor_id: int,
        amount: int,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> list[BalanceMutationResult]:
        self._validate_positive_amount(amount)
        reason = self._require_reason(reason)
        settings = await self._repository.get_guild_settings(guild_id)
        if amount > settings.max_admin_grant_per_use:
            raise EconomyValidationError(
                f"A quantidade maxima por uso e {settings.max_admin_grant_per_use}."
            )

        unique_user_ids = list(dict.fromkeys(user_ids))
        if not unique_user_ids:
            raise EconomyValidationError("Nenhum usuario elegivel foi encontrado.")

        results: list[BalanceMutationResult] = []
        operation_metadata = {"source": "admin_role_command"}
        if metadata:
            operation_metadata.update(metadata)

        for user_id in unique_user_ids:
            result = await self._repository.mutate_balance(
                guild_id=guild_id,
                user_id=user_id,
                amount=amount,
                transaction_type=EconomyTransactionType.ADMIN_GIVE,
                actor_id=actor_id,
                reason=reason,
                metadata=operation_metadata,
            )
            await self._repository.record_audit_log(
                guild_id=guild_id,
                actor_id=actor_id,
                action=EconomyTransactionType.ADMIN_GIVE.value,
                target_user_id=user_id,
                before_data={"balance": result.transaction.balance_before},
                after_data={
                    "balance": result.transaction.balance_after,
                    "amount": amount,
                    "bulk": True,
                },
                reason=reason,
            )
            results.append(result)

        return results

    async def claim_daily_gift(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> BotRewardClaimResult:
        today = utc_now().astimezone(self.DAILY_GIFT_TIMEZONE).date().isoformat()
        claimed = await self._repository.try_claim_reward(
            guild_id=guild_id,
            user_id=user_id,
            reward_key=self.DAILY_GIFT_KEY,
            claim_date=today,
            once=False,
        )
        if not claimed:
            raise EconomyValidationError("Voce ja resgatou seu presente diario hoje.")

        amount = random.SystemRandom().randint(
            self.DAILY_GIFT_MIN,
            self.DAILY_GIFT_MAX,
        )
        result = await self._repository.mutate_balance(
            guild_id=guild_id,
            user_id=user_id,
            amount=amount,
            transaction_type=EconomyTransactionType.BOT_REWARD,
            actor_id=None,
            reason="daily_gift",
            metadata={
                "source": "bot_announcement_panel",
                "reward_key": self.DAILY_GIFT_KEY,
            },
        )
        return BotRewardClaimResult(
            wallet=result.wallet,
            transaction=result.transaction,
            reward_key=self.DAILY_GIFT_KEY,
            amount=amount,
        )

    async def claim_starter_pack(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> BotRewardClaimResult:
        claimed = await self._repository.try_claim_reward(
            guild_id=guild_id,
            user_id=user_id,
            reward_key=self.STARTER_PACK_KEY,
            claim_date=None,
            once=True,
        )
        if not claimed:
            raise EconomyValidationError("Voce ja resgatou seu pacote inicial.")

        result = await self._repository.mutate_balance(
            guild_id=guild_id,
            user_id=user_id,
            amount=self.STARTER_PACK_AMOUNT,
            transaction_type=EconomyTransactionType.BOT_REWARD,
            actor_id=None,
            reason="starter_pack",
            metadata={
                "source": "bot_announcement_panel",
                "reward_key": self.STARTER_PACK_KEY,
            },
        )
        return BotRewardClaimResult(
            wallet=result.wallet,
            transaction=result.transaction,
            reward_key=self.STARTER_PACK_KEY,
            amount=self.STARTER_PACK_AMOUNT,
        )

    async def remove_points(
        self,
        *,
        guild_id: int,
        user_id: int,
        actor_id: int,
        amount: int,
        reason: str,
    ) -> BalanceMutationResult:
        self._validate_positive_amount(amount)
        reason = self._require_reason(reason)
        try:
            result = await self._repository.mutate_balance(
                guild_id=guild_id,
                user_id=user_id,
                amount=-amount,
                transaction_type=EconomyTransactionType.ADMIN_REMOVE,
                actor_id=actor_id,
                reason=reason,
                metadata={"source": "admin_command"},
            )
        except ValueError as exc:
            raise EconomyValidationError(str(exc)) from exc

        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action=EconomyTransactionType.ADMIN_REMOVE.value,
            target_user_id=user_id,
            before_data={"balance": result.transaction.balance_before},
            after_data={"balance": result.transaction.balance_after, "amount": -amount},
            reason=reason,
        )
        return result

    @staticmethod
    def _validate_positive_amount(amount: int) -> None:
        if amount <= 0:
            raise EconomyValidationError("A quantidade precisa ser maior que zero.")

    @staticmethod
    def _require_reason(reason: str) -> str:
        normalized = reason.strip()
        if not normalized:
            raise EconomyValidationError("Informe um motivo para a operacao.")
        if len(normalized) > 500:
            raise EconomyValidationError("O motivo nao pode passar de 500 caracteres.")
        return normalized
