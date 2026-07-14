from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.models.activity import ActivityStats, NativeVoiceSession
from app.models.audit import AdminAuditLog
from app.models.economy import (
    ActivityConversionResult,
    BalanceMutationResult,
    CreditProtectionAdjustmentResult,
    CreditProtectionResult,
    CreditProtectionState,
    EconomyTransaction,
    EconomyTransactionType,
    SavingsOperationResult,
    SavingsOverview,
    UserGameProgressSummary,
    UserProfileResetResult,
    UserTransferResult,
    UserWallet,
)
from app.models.guild_settings import GuildEconomySettings
from app.models.shop import (
    LevelConfig,
    LevelUpgradePurchase,
    LevelUpgradeResult,
    RewardItem,
    RewardItemCreate,
    RewardPurchase,
    ShopPurchaseResult,
)


class EconomyRepositoryProtocol(Protocol):
    """Contrato de economia independente da implementacao PostgreSQL."""

    async def get_guild_settings(self, guild_id: int) -> GuildEconomySettings: ...

    async def update_guild_settings(
        self, guild_id: int, updates: dict[str, Any]
    ) -> GuildEconomySettings: ...

    async def get_admin_summary(self, guild_id: int) -> dict[str, Any]: ...

    async def get_wallet(self, guild_id: int, user_id: int) -> UserWallet: ...

    async def get_credit_protection_state(
        self, guild_id: int, user_id: int
    ) -> CreditProtectionState: ...

    async def adjust_credit_saves(
        self, *, guild_id: int, user_id: int, delta: int
    ) -> CreditProtectionAdjustmentResult: ...

    async def apply_credit_protection(
        self,
        *,
        guild_id: int,
        user_id: int,
        game_key: str,
        stake: int,
        is_loss: bool,
        metadata: dict[str, Any] | None = None,
    ) -> CreditProtectionResult: ...

    async def get_savings_overview(
        self, *, guild_id: int, user_id: int, daily_interest_bps: int
    ) -> SavingsOverview: ...

    async def deposit_savings(
        self,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
        daily_interest_bps: int,
    ) -> SavingsOperationResult: ...

    async def withdraw_savings(
        self,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
        daily_interest_bps: int,
    ) -> SavingsOperationResult: ...

    async def reset_user_profile(
        self, guild_id: int, user_id: int
    ) -> UserProfileResetResult: ...

    async def mutate_balance(
        self,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
        transaction_type: EconomyTransactionType,
        actor_id: int | None,
        reason: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> BalanceMutationResult: ...

    async def grant_achievement_reward_once(
        self,
        *,
        guild_id: int,
        user_id: int,
        achievement_key: str,
        amount: int,
    ) -> BalanceMutationResult | None: ...

    async def transfer_balance(
        self,
        *,
        guild_id: int,
        sender_id: int,
        receiver_id: int,
        amount: int,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> UserTransferResult: ...

    async def list_transactions(
        self, guild_id: int, user_id: int, *, limit: int = 10
    ) -> list[EconomyTransaction]: ...

    async def list_casino_transactions(
        self, guild_id: int, *, limit: int = 500
    ) -> list[EconomyTransaction]: ...

    async def get_user_game_progress_summary(
        self, guild_id: int, user_id: int
    ) -> UserGameProgressSummary: ...

    async def get_user_casino_profit_since(
        self, guild_id: int, user_id: int, since: datetime
    ) -> int: ...

    async def count_user_scratch_card_purchases_since(
        self, guild_id: int, user_id: int, since: datetime
    ) -> int: ...

    async def list_top_wallets(
        self, guild_id: int, *, limit: int = 10
    ) -> list[UserWallet]: ...

    async def record_audit_log(
        self,
        *,
        guild_id: int,
        actor_id: int,
        action: str,
        target_user_id: int | None = None,
        target_resource_id: str | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> AdminAuditLog: ...

    async def try_claim_reward(
        self,
        *,
        guild_id: int,
        user_id: int,
        reward_key: str,
        claim_date: str | None,
        once: bool,
    ) -> bool: ...

    async def record_message_activity(
        self, *, guild_id: int, channel_id: int, user_id: int
    ) -> None: ...

    async def start_voice_session(
        self, *, guild_id: int, user_id: int, channel_id: int
    ) -> NativeVoiceSession: ...

    async def close_voice_sessions(
        self,
        *,
        guild_id: int,
        user_id: int,
        invalid_reason: str | None = None,
    ) -> list[NativeVoiceSession]: ...

    async def get_activity_stats(
        self, guild_id: int, user_id: int
    ) -> ActivityStats: ...

    async def convert_activity(
        self, *, stats: ActivityStats, actor_id: int
    ) -> ActivityConversionResult: ...

    async def create_reward(self, reward: RewardItemCreate) -> RewardItem: ...

    async def list_rewards(
        self, guild_id: int, *, include_inactive: bool = False
    ) -> list[RewardItem]: ...

    async def get_reward(self, reward_id: int) -> RewardItem | None: ...

    async def update_reward(
        self, *, guild_id: int, reward_id: int, updates: dict[str, Any]
    ) -> RewardItem | None: ...

    async def remove_reward(
        self, *, guild_id: int, reward_id: int
    ) -> RewardItem | None: ...

    async def purchase_reward(
        self,
        *,
        guild_id: int,
        user_id: int,
        reward_id: int,
        metadata: dict[str, Any] | None = None,
    ) -> ShopPurchaseResult: ...

    async def list_purchases(
        self, guild_id: int, user_id: int, *, limit: int = 10
    ) -> list[RewardPurchase]: ...

    async def upsert_level_config(
        self,
        *,
        guild_id: int,
        level: int,
        role_id: int,
        price: int,
        is_active: bool,
        created_by: int,
        saves_reward: int = 0,
    ) -> LevelConfig: ...

    async def list_level_configs(
        self, guild_id: int, *, include_inactive: bool = False
    ) -> list[LevelConfig]: ...

    async def get_level_config(
        self, guild_id: int, level: int
    ) -> LevelConfig | None: ...

    async def list_user_level_upgrades(
        self, guild_id: int, user_id: int
    ) -> list[LevelUpgradePurchase]: ...

    async def purchase_level_upgrade(
        self, *, guild_id: int, user_id: int, level: int
    ) -> LevelUpgradeResult: ...
