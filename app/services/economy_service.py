from __future__ import annotations

import random
from datetime import timedelta, timezone

from app.models.economy import (
    BalanceMutationResult,
    BotRewardClaimResult,
    CreditProtectionAdjustmentResult,
    CreditProtectionState,
    EconomyTransaction,
    EconomyTransactionType,
    SavingsOperationResult,
    SavingsOverview,
    UserProfileResetResult,
    UserTransferResult,
    UserWallet,
)
from app.models.giveaway import utc_now
from app.models.guild_settings import GuildEconomySettings
from app.repositories.economy_repository import SQLiteEconomyRepository


class EconomyServiceError(Exception):
    """Erro base da economia."""


class EconomyValidationError(EconomyServiceError):
    """Erro de validacao de entrada da economia."""


CASINO_MIN_BET_FIELDS: dict[str, str] = {
    "casino_min_bet_coin_flip": "cara ou coroa",
    "casino_min_bet_dice": "dados",
    "casino_min_bet_slot": "slot",
    "casino_min_bet_roulette": "roleta",
    "casino_min_bet_mascot_race": "corrida de mascotes",
    "casino_min_bet_duel": "duelo",
    "casino_min_bet_blackjack": "BlackJack",
    "casino_min_bet_scratch_card": "raspadinha",
    "casino_min_bet_collective_race": "corrida coletiva",
    "casino_min_bet_match_bet": "bets de partidas",
    "casino_min_bet_truco": "Truco",
}


class EconomyService:
    """Regras de carteira, saldo, transacoes e ajustes administrativos."""

    DAILY_GIFT_KEY = "daily_gift"
    STARTER_PACK_KEY = "starter_pack"
    DAILY_GIFT_MIN = 25
    DAILY_GIFT_MAX = 75
    STARTER_PACK_AMOUNT = 500
    DAILY_GIFT_TIMEZONE = timezone(timedelta(hours=-3))

    def __init__(self, repository: SQLiteEconomyRepository) -> None:
        self._repository = repository

    async def get_wallet(self, guild_id: int, user_id: int) -> UserWallet:
        return await self._repository.get_wallet(guild_id, user_id)

    async def get_credit_protection_state(
        self,
        guild_id: int,
        user_id: int,
    ) -> CreditProtectionState:
        return await self._repository.get_credit_protection_state(guild_id, user_id)

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

    async def transfer_points(
        self,
        *,
        guild_id: int,
        sender_id: int,
        receiver_id: int,
        amount: int,
    ) -> UserTransferResult:
        self._validate_positive_amount(amount)
        if sender_id == receiver_id:
            raise EconomyValidationError(
                "Voce nao pode transferir pontos para si mesmo."
            )
        try:
            return await self._repository.transfer_balance(
                guild_id=guild_id,
                sender_id=sender_id,
                receiver_id=receiver_id,
                amount=amount,
                reason="user_transfer",
                metadata={"source": "economy_panel"},
            )
        except ValueError as exc:
            raise EconomyValidationError(str(exc)) from exc

    async def reset_user_profile(
        self,
        *,
        guild_id: int,
        user_id: int,
        actor_id: int,
        reason: str,
        related_counts: dict[str, int] | None = None,
    ) -> UserProfileResetResult:
        reason = self._require_reason(reason)
        result = await self._repository.reset_user_profile(guild_id, user_id)
        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="USER_PROFILE_RESET",
            target_user_id=user_id,
            before_data={
                "wallet": self._wallet_audit_data(result.wallet_before),
            },
            after_data={
                "wallet": {"balance": 0, "total_earned": 0, "total_spent": 0},
                "deleted": {
                    "transactions": result.deleted_transactions,
                    "reward_claims": result.deleted_reward_claims,
                    "activity_cursors": result.deleted_activity_cursors,
                    "message_stats": result.deleted_message_stats,
                    "voice_sessions": result.deleted_voice_sessions,
                    "purchases": result.deleted_purchases,
                    "wallets": result.deleted_wallets,
                    "credit_protection": result.deleted_credit_protection,
                    "savings_accounts": result.deleted_savings_accounts,
                },
                "related_deleted": related_counts or {},
            },
            reason=reason,
        )
        return result

    async def configure_settings(
        self,
        *,
        guild_id: int,
        actor_id: int,
        currency_name: str | None = None,
        voice_points_per_minute: int | None = None,
        message_points: int | None = None,
        min_voice_seconds_to_claim: int | None = None,
        min_messages_to_claim: int | None = None,
        ignore_afk_channel: bool | None = None,
        count_voice_when_alone: bool | None = None,
        max_admin_grant_per_use: int | None = None,
        casino_max_bet: int | None = None,
        casino_daily_profit_limit: int | None = None,
        casino_min_bet_coin_flip: int | None = None,
        casino_min_bet_dice: int | None = None,
        casino_min_bet_slot: int | None = None,
        casino_min_bet_roulette: int | None = None,
        casino_min_bet_mascot_race: int | None = None,
        casino_min_bet_duel: int | None = None,
        casino_min_bet_blackjack: int | None = None,
        casino_min_bet_scratch_card: int | None = None,
        casino_min_bet_collective_race: int | None = None,
        casino_min_bet_match_bet: int | None = None,
        casino_min_bet_truco: int | None = None,
        casino_limiters_enabled: bool | None = None,
        savings_daily_interest_percent: float | None = None,
        economy_manager_role_id: int | None = None,
        economy_channel_id: int | None = None,
        shop_channel_id: int | None = None,
        staff_log_channel_id: int | None = None,
    ) -> GuildEconomySettings:
        before = await self._repository.get_guild_settings(guild_id)
        updates: dict[str, object | None] = {}

        if currency_name is not None:
            normalized_currency = currency_name.strip()
            if not normalized_currency:
                raise EconomyValidationError("O nome da moeda nao pode ficar vazio.")
            if len(normalized_currency) > 32:
                raise EconomyValidationError("O nome da moeda deve ter ate 32 letras.")
            updates["currency_name"] = normalized_currency
        if voice_points_per_minute is not None:
            self._validate_non_negative(
                voice_points_per_minute,
                "Os pontos por minuto nao podem ser negativos.",
            )
            updates["voice_points_per_minute"] = voice_points_per_minute
        if message_points is not None:
            self._validate_non_negative(
                message_points,
                "Os pontos por mensagem nao podem ser negativos.",
            )
            updates["message_points"] = message_points
        if min_voice_seconds_to_claim is not None:
            self._validate_positive_value(
                min_voice_seconds_to_claim,
                "O minimo de segundos em call precisa ser positivo.",
            )
            updates["min_voice_seconds_to_claim"] = min_voice_seconds_to_claim
        if min_messages_to_claim is not None:
            self._validate_positive_value(
                min_messages_to_claim,
                "O minimo de mensagens precisa ser positivo.",
            )
            updates["min_messages_to_claim"] = min_messages_to_claim
        if ignore_afk_channel is not None:
            updates["ignore_afk_channel"] = int(ignore_afk_channel)
        if count_voice_when_alone is not None:
            updates["count_voice_when_alone"] = int(count_voice_when_alone)
        if max_admin_grant_per_use is not None:
            self._validate_positive_value(
                max_admin_grant_per_use,
                "O limite administrativo precisa ser positivo.",
            )
            updates["max_admin_grant_per_use"] = max_admin_grant_per_use
        if casino_max_bet is not None:
            self._validate_positive_value(
                casino_max_bet,
                "O limite de aposta precisa ser positivo.",
            )
            updates["casino_max_bet"] = casino_max_bet
        if casino_daily_profit_limit is not None:
            self._validate_non_negative(
                casino_daily_profit_limit,
                "O teto diario de lucro nao pode ser negativo.",
            )
            updates["casino_daily_profit_limit"] = casino_daily_profit_limit
        if casino_limiters_enabled is not None:
            updates["casino_limiters_enabled"] = int(casino_limiters_enabled)
        if savings_daily_interest_percent is not None:
            updates["savings_daily_interest_bps"] = self._percent_to_bps(
                savings_daily_interest_percent
            )
        min_bet_updates = {
            "casino_min_bet_coin_flip": casino_min_bet_coin_flip,
            "casino_min_bet_dice": casino_min_bet_dice,
            "casino_min_bet_slot": casino_min_bet_slot,
            "casino_min_bet_roulette": casino_min_bet_roulette,
            "casino_min_bet_mascot_race": casino_min_bet_mascot_race,
            "casino_min_bet_duel": casino_min_bet_duel,
            "casino_min_bet_blackjack": casino_min_bet_blackjack,
            "casino_min_bet_scratch_card": casino_min_bet_scratch_card,
            "casino_min_bet_collective_race": casino_min_bet_collective_race,
            "casino_min_bet_match_bet": casino_min_bet_match_bet,
            "casino_min_bet_truco": casino_min_bet_truco,
        }
        for field, value in min_bet_updates.items():
            if value is None:
                continue
            self._validate_positive_value(
                value,
                f"O minimo de aposta de {CASINO_MIN_BET_FIELDS[field]} "
                "precisa ser positivo.",
            )
            updates[field] = value
        self._validate_min_bets_against_max(before, updates)
        if economy_manager_role_id is not None:
            updates["economy_manager_role_id"] = economy_manager_role_id or None
        if economy_channel_id is not None:
            updates["economy_channel_id"] = economy_channel_id
        if shop_channel_id is not None:
            updates["shop_channel_id"] = shop_channel_id
        if staff_log_channel_id is not None:
            updates["staff_log_channel_id"] = staff_log_channel_id

        if not updates:
            raise EconomyValidationError("Informe ao menos uma configuracao.")

        after = await self._repository.update_guild_settings(guild_id, updates)
        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="ECONOMY_CONFIG_UPDATE",
            before_data=self._settings_audit_data(before),
            after_data=self._settings_audit_data(after),
            reason="economy_config",
        )
        return after

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

    async def get_savings_overview(
        self,
        guild_id: int,
        user_id: int,
    ) -> SavingsOverview:
        settings = await self._repository.get_guild_settings(guild_id)
        return await self._repository.get_savings_overview(
            guild_id=guild_id,
            user_id=user_id,
            daily_interest_bps=settings.savings_daily_interest_bps,
        )

    async def deposit_savings(
        self,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
    ) -> SavingsOperationResult:
        self._validate_positive_amount(amount)
        settings = await self._repository.get_guild_settings(guild_id)
        try:
            return await self._repository.deposit_savings(
                guild_id=guild_id,
                user_id=user_id,
                amount=amount,
                daily_interest_bps=settings.savings_daily_interest_bps,
            )
        except ValueError as exc:
            raise EconomyValidationError(str(exc)) from exc

    async def withdraw_savings(
        self,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
    ) -> SavingsOperationResult:
        self._validate_positive_amount(amount)
        settings = await self._repository.get_guild_settings(guild_id)
        try:
            return await self._repository.withdraw_savings(
                guild_id=guild_id,
                user_id=user_id,
                amount=amount,
                daily_interest_bps=settings.savings_daily_interest_bps,
            )
        except ValueError as exc:
            raise EconomyValidationError(str(exc)) from exc

    async def add_credit_saves(
        self,
        *,
        guild_id: int,
        user_id: int,
        actor_id: int,
        amount: int,
        reason: str,
    ) -> CreditProtectionAdjustmentResult:
        self._validate_positive_amount(amount)
        reason = self._require_reason(reason)
        result = await self._repository.adjust_credit_saves(
            guild_id=guild_id,
            user_id=user_id,
            delta=amount,
        )
        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="CREDIT_SAVES_ADD",
            target_user_id=user_id,
            before_data=self._credit_state_audit_data(result.before),
            after_data=self._credit_state_audit_data(result.after),
            reason=reason,
        )
        return result

    async def remove_credit_saves(
        self,
        *,
        guild_id: int,
        user_id: int,
        actor_id: int,
        amount: int,
        reason: str,
    ) -> CreditProtectionAdjustmentResult:
        self._validate_positive_amount(amount)
        reason = self._require_reason(reason)
        try:
            result = await self._repository.adjust_credit_saves(
                guild_id=guild_id,
                user_id=user_id,
                delta=-amount,
            )
        except ValueError as exc:
            raise EconomyValidationError(str(exc)) from exc
        await self._repository.record_audit_log(
            guild_id=guild_id,
            actor_id=actor_id,
            action="CREDIT_SAVES_REMOVE",
            target_user_id=user_id,
            before_data=self._credit_state_audit_data(result.before),
            after_data=self._credit_state_audit_data(result.after),
            reason=reason,
        )
        return result

    @staticmethod
    def _validate_positive_amount(amount: int) -> None:
        if amount <= 0:
            raise EconomyValidationError("A quantidade precisa ser maior que zero.")

    @staticmethod
    def _validate_positive_value(value: int, message: str) -> None:
        if value <= 0:
            raise EconomyValidationError(message)

    @staticmethod
    def _validate_non_negative(value: int, message: str) -> None:
        if value < 0:
            raise EconomyValidationError(message)

    @staticmethod
    def _require_reason(reason: str) -> str:
        normalized = reason.strip()
        if not normalized:
            raise EconomyValidationError("Informe um motivo para a operacao.")
        if len(normalized) > 500:
            raise EconomyValidationError("O motivo nao pode passar de 500 caracteres.")
        return normalized

    @staticmethod
    def _validate_min_bets_against_max(
        current: GuildEconomySettings,
        updates: dict[str, object | None],
    ) -> None:
        max_bet = int(updates.get("casino_max_bet", current.casino_max_bet) or 0)
        for field, label in CASINO_MIN_BET_FIELDS.items():
            min_bet = int(updates.get(field, getattr(current, field)) or 0)
            if min_bet > max_bet:
                raise EconomyValidationError(
                    f"O minimo de aposta de {label} nao pode ser maior que "
                    f"o limite maximo de aposta ({max_bet})."
                )

    @staticmethod
    def _settings_audit_data(settings: GuildEconomySettings) -> dict[str, object]:
        return {
            "currency_name": settings.currency_name,
            "voice_points_per_minute": settings.voice_points_per_minute,
            "message_points": settings.message_points,
            "min_voice_seconds_to_claim": settings.min_voice_seconds_to_claim,
            "min_messages_to_claim": settings.min_messages_to_claim,
            "ignore_afk_channel": settings.ignore_afk_channel,
            "count_voice_when_alone": settings.count_voice_when_alone,
            "max_admin_grant_per_use": settings.max_admin_grant_per_use,
            "casino_max_bet": settings.casino_max_bet,
            "casino_daily_profit_limit": settings.casino_daily_profit_limit,
            "casino_min_bet_coin_flip": settings.casino_min_bet_coin_flip,
            "casino_min_bet_dice": settings.casino_min_bet_dice,
            "casino_min_bet_slot": settings.casino_min_bet_slot,
            "casino_min_bet_roulette": settings.casino_min_bet_roulette,
            "casino_min_bet_mascot_race": settings.casino_min_bet_mascot_race,
            "casino_min_bet_duel": settings.casino_min_bet_duel,
            "casino_min_bet_blackjack": settings.casino_min_bet_blackjack,
            "casino_min_bet_scratch_card": settings.casino_min_bet_scratch_card,
            "casino_min_bet_collective_race": settings.casino_min_bet_collective_race,
            "casino_min_bet_match_bet": settings.casino_min_bet_match_bet,
            "casino_min_bet_truco": settings.casino_min_bet_truco,
            "casino_limiters_enabled": settings.casino_limiters_enabled,
            "savings_daily_interest_bps": settings.savings_daily_interest_bps,
            "economy_manager_role_id": settings.economy_manager_role_id,
            "economy_channel_id": settings.economy_channel_id,
            "shop_channel_id": settings.shop_channel_id,
            "staff_log_channel_id": settings.staff_log_channel_id,
        }

    @staticmethod
    def _wallet_audit_data(wallet: UserWallet | None) -> dict[str, int] | None:
        if wallet is None:
            return None
        return {
            "balance": wallet.balance,
            "total_earned": wallet.total_earned,
            "total_spent": wallet.total_spent,
        }

    @staticmethod
    def _credit_state_audit_data(
        state: CreditProtectionState,
    ) -> dict[str, int | str]:
        return {
            "guild_id": state.guild_id,
            "user_id": state.user_id,
            "saves": state.saves,
            "lose_streak": state.lose_streak,
            "updated_at": state.updated_at.isoformat(),
        }

    @staticmethod
    def _percent_to_bps(value: float) -> int:
        if value < 0:
            raise EconomyValidationError("A taxa da poupança não pode ser negativa.")
        if value > 100:
            raise EconomyValidationError(
                "A taxa da poupança deve ficar entre 0 e 100% ao dia."
            )
        return int(round(value * 100))
