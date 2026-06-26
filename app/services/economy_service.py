from __future__ import annotations

from app.models.economy import (
    BalanceMutationResult,
    EconomyTransaction,
    EconomyTransactionType,
    UserWallet,
)
from app.repositories.economy_repository import SQLiteEconomyRepository


class EconomyServiceError(Exception):
    """Erro base da economia."""


class EconomyValidationError(EconomyServiceError):
    """Erro de validacao de entrada da economia."""


class EconomyService:
    """Regras de carteira, saldo, transacoes e ajustes administrativos."""

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
