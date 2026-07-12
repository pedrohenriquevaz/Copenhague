from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.models.activity import ActivityStats, NativeVoiceSession
from app.models.audit import AdminAuditLog
from app.models.economy import (
    ActivityClaimCursor,
    ActivityConversionResult,
    BalanceMutationResult,
    CreditProtectionAdjustmentResult,
    CreditProtectionResult,
    CreditProtectionState,
    EconomyTransaction,
    EconomyTransactionType,
    SavingsAccount,
    SavingsOperationResult,
    SavingsOverview,
    UserGameProgressSummary,
    UserProfileResetResult,
    UserTransferResult,
    UserWallet,
)
from app.models.giveaway import parse_datetime, serialize_datetime, utc_now
from app.models.guild_settings import GuildEconomySettings
from app.models.shop import (
    DeliveryStatus,
    LevelConfig,
    LevelUpgradePurchase,
    LevelUpgradeResult,
    LevelUpgradeStatus,
    PurchaseStatus,
    RewardItem,
    RewardItemCreate,
    RewardPurchase,
    RewardType,
    ShopPurchaseResult,
    ShopPurchaseStatus,
    StockMode,
)


class SQLiteEconomyRepository:
    """Persistencia SQLite para economia, atividade, loja e auditoria."""

    CREDIT_CASHBACK_LOW_STREAK = 4
    CREDIT_CASHBACK_HIGH_STREAK = 5
    CREDIT_CASHBACK_LOW_PERCENT = 50
    CREDIT_CASHBACK_HIGH_PERCENT = 80
    SAVINGS_MAX_DEPOSIT_PERCENT = 70
    SAVINGS_LOCK_DAYS = 1

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize_schema()

    async def get_guild_settings(self, guild_id: int) -> GuildEconomySettings:
        return await asyncio.to_thread(self._get_or_create_settings_sync, guild_id)

    async def update_guild_settings(
        self,
        guild_id: int,
        updates: dict[str, Any],
    ) -> GuildEconomySettings:
        return await asyncio.to_thread(
            self._update_guild_settings_sync,
            guild_id,
            updates,
        )

    async def get_admin_summary(self, guild_id: int) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_admin_summary_sync, guild_id)

    async def get_wallet(self, guild_id: int, user_id: int) -> UserWallet:
        return await asyncio.to_thread(
            self._get_or_create_wallet_sync,
            guild_id,
            user_id,
        )

    async def get_credit_protection_state(
        self,
        guild_id: int,
        user_id: int,
    ) -> CreditProtectionState:
        return await asyncio.to_thread(
            self._get_or_create_credit_protection_state_sync,
            guild_id,
            user_id,
        )

    async def adjust_credit_saves(
        self,
        *,
        guild_id: int,
        user_id: int,
        delta: int,
    ) -> CreditProtectionAdjustmentResult:
        return await asyncio.to_thread(
            self._adjust_credit_saves_sync,
            guild_id,
            user_id,
            delta,
        )

    async def apply_credit_protection(
        self,
        *,
        guild_id: int,
        user_id: int,
        game_key: str,
        stake: int,
        is_loss: bool,
        metadata: dict[str, Any] | None = None,
    ) -> CreditProtectionResult:
        return await asyncio.to_thread(
            self._apply_credit_protection_sync,
            guild_id,
            user_id,
            game_key,
            stake,
            is_loss,
            metadata or {},
        )

    async def get_savings_overview(
        self,
        *,
        guild_id: int,
        user_id: int,
        daily_interest_bps: int,
    ) -> SavingsOverview:
        return await asyncio.to_thread(
            self._get_savings_overview_sync,
            guild_id,
            user_id,
            daily_interest_bps,
        )

    async def deposit_savings(
        self,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
        daily_interest_bps: int,
    ) -> SavingsOperationResult:
        return await asyncio.to_thread(
            self._deposit_savings_sync,
            guild_id,
            user_id,
            amount,
            daily_interest_bps,
        )

    async def withdraw_savings(
        self,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
        daily_interest_bps: int,
    ) -> SavingsOperationResult:
        return await asyncio.to_thread(
            self._withdraw_savings_sync,
            guild_id,
            user_id,
            amount,
            daily_interest_bps,
        )

    async def reset_user_profile(
        self,
        guild_id: int,
        user_id: int,
    ) -> UserProfileResetResult:
        return await asyncio.to_thread(
            self._reset_user_profile_sync,
            guild_id,
            user_id,
        )

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
    ) -> BalanceMutationResult:
        return await asyncio.to_thread(
            self._mutate_balance_sync,
            guild_id,
            user_id,
            amount,
            transaction_type,
            actor_id,
            reason,
            metadata or {},
        )

    async def grant_achievement_reward_once(
        self,
        *,
        guild_id: int,
        user_id: int,
        achievement_key: str,
        amount: int,
    ) -> BalanceMutationResult | None:
        return await asyncio.to_thread(
            self._grant_achievement_reward_once_sync,
            guild_id,
            user_id,
            achievement_key,
            amount,
        )

    async def transfer_balance(
        self,
        *,
        guild_id: int,
        sender_id: int,
        receiver_id: int,
        amount: int,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> UserTransferResult:
        return await asyncio.to_thread(
            self._transfer_balance_sync,
            guild_id,
            sender_id,
            receiver_id,
            amount,
            reason,
            metadata or {},
        )

    async def list_transactions(
        self,
        guild_id: int,
        user_id: int,
        *,
        limit: int = 10,
    ) -> list[EconomyTransaction]:
        return await asyncio.to_thread(
            self._list_transactions_sync,
            guild_id,
            user_id,
            limit,
        )

    async def list_casino_transactions(
        self,
        guild_id: int,
        *,
        limit: int = 500,
    ) -> list[EconomyTransaction]:
        return await asyncio.to_thread(
            self._list_casino_transactions_sync,
            guild_id,
            limit,
        )

    async def get_user_game_progress_summary(
        self,
        guild_id: int,
        user_id: int,
    ) -> UserGameProgressSummary:
        return await asyncio.to_thread(
            self._get_user_game_progress_summary_sync,
            guild_id,
            user_id,
        )

    async def get_user_casino_profit_since(
        self,
        guild_id: int,
        user_id: int,
        since,
    ) -> int:
        return await asyncio.to_thread(
            self._get_user_casino_profit_since_sync,
            guild_id,
            user_id,
            serialize_datetime(since),
        )

    async def count_user_scratch_card_purchases_since(
        self,
        guild_id: int,
        user_id: int,
        since,
    ) -> int:
        return await asyncio.to_thread(
            self._count_user_scratch_card_purchases_since_sync,
            guild_id,
            user_id,
            serialize_datetime(since),
        )

    async def list_top_wallets(
        self,
        guild_id: int,
        *,
        limit: int = 10,
    ) -> list[UserWallet]:
        return await asyncio.to_thread(self._list_top_wallets_sync, guild_id, limit)

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
    ) -> AdminAuditLog:
        return await asyncio.to_thread(
            self._record_audit_log_sync,
            guild_id,
            actor_id,
            action,
            target_user_id,
            target_resource_id,
            before_data or {},
            after_data or {},
            reason,
        )

    async def try_claim_reward(
        self,
        *,
        guild_id: int,
        user_id: int,
        reward_key: str,
        claim_date: str | None,
        once: bool,
    ) -> bool:
        return await asyncio.to_thread(
            self._try_claim_reward_sync,
            guild_id,
            user_id,
            reward_key,
            claim_date,
            once,
        )

    async def record_message_activity(
        self,
        *,
        guild_id: int,
        channel_id: int,
        user_id: int,
    ) -> None:
        await asyncio.to_thread(
            self._record_message_activity_sync,
            guild_id,
            channel_id,
            user_id,
        )

    async def start_voice_session(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
    ) -> NativeVoiceSession:
        return await asyncio.to_thread(
            self._start_voice_session_sync,
            guild_id,
            user_id,
            channel_id,
        )

    async def close_voice_sessions(
        self,
        *,
        guild_id: int,
        user_id: int,
        invalid_reason: str | None = None,
    ) -> list[NativeVoiceSession]:
        return await asyncio.to_thread(
            self._close_voice_sessions_sync,
            guild_id,
            user_id,
            invalid_reason,
        )

    async def get_activity_stats(self, guild_id: int, user_id: int) -> ActivityStats:
        return await asyncio.to_thread(self._get_activity_stats_sync, guild_id, user_id)

    async def convert_activity(
        self,
        *,
        stats: ActivityStats,
        actor_id: int,
    ) -> ActivityConversionResult:
        return await asyncio.to_thread(self._convert_activity_sync, stats, actor_id)

    async def create_reward(self, reward: RewardItemCreate) -> RewardItem:
        return await asyncio.to_thread(self._create_reward_sync, reward)

    async def list_rewards(
        self,
        guild_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[RewardItem]:
        return await asyncio.to_thread(
            self._list_rewards_sync,
            guild_id,
            include_inactive,
        )

    async def get_reward(self, reward_id: int) -> RewardItem | None:
        return await asyncio.to_thread(self._get_reward_sync, reward_id)

    async def update_reward(
        self,
        *,
        guild_id: int,
        reward_id: int,
        updates: dict[str, Any],
    ) -> RewardItem | None:
        return await asyncio.to_thread(
            self._update_reward_sync,
            guild_id,
            reward_id,
            updates,
        )

    async def remove_reward(
        self,
        *,
        guild_id: int,
        reward_id: int,
    ) -> RewardItem | None:
        return await asyncio.to_thread(
            self._remove_reward_sync,
            guild_id,
            reward_id,
        )

    async def purchase_reward(
        self,
        *,
        guild_id: int,
        user_id: int,
        reward_id: int,
        metadata: dict[str, Any] | None = None,
    ) -> ShopPurchaseResult:
        return await asyncio.to_thread(
            self._purchase_reward_sync,
            guild_id,
            user_id,
            reward_id,
            metadata or {},
        )

    async def list_purchases(
        self,
        guild_id: int,
        user_id: int,
        *,
        limit: int = 10,
    ) -> list[RewardPurchase]:
        return await asyncio.to_thread(
            self._list_purchases_sync,
            guild_id,
            user_id,
            limit,
        )

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
    ) -> LevelConfig:
        return await asyncio.to_thread(
            self._upsert_level_config_sync,
            guild_id,
            level,
            role_id,
            price,
            is_active,
            created_by,
            saves_reward,
        )

    async def list_level_configs(
        self,
        guild_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[LevelConfig]:
        return await asyncio.to_thread(
            self._list_level_configs_sync,
            guild_id,
            include_inactive,
        )

    async def get_level_config(
        self,
        guild_id: int,
        level: int,
    ) -> LevelConfig | None:
        return await asyncio.to_thread(
            self._get_level_config_sync,
            guild_id,
            level,
        )

    async def list_user_level_upgrades(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[LevelUpgradePurchase]:
        return await asyncio.to_thread(
            self._list_user_level_upgrades_sync,
            guild_id,
            user_id,
        )

    async def purchase_level_upgrade(
        self,
        *,
        guild_id: int,
        user_id: int,
        level: int,
    ) -> LevelUpgradeResult:
        return await asyncio.to_thread(
            self._purchase_level_upgrade_sync,
            guild_id,
            user_id,
            level,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
        return connection

    def _initialize_schema(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS guild_settings (
                        guild_id INTEGER PRIMARY KEY,
                        currency_name TEXT NOT NULL DEFAULT 'pontos',
                        voice_points_per_minute INTEGER NOT NULL DEFAULT 2,
                        message_points INTEGER NOT NULL DEFAULT 1,
                        activity_provider TEXT NOT NULL DEFAULT 'native',
                        economy_channel_id INTEGER,
                        shop_channel_id INTEGER,
                        staff_log_channel_id INTEGER,
                        min_voice_seconds_to_claim INTEGER NOT NULL DEFAULT 60,
                        min_messages_to_claim INTEGER NOT NULL DEFAULT 1,
                        ignore_afk_channel INTEGER NOT NULL DEFAULT 1,
                        ignore_bots INTEGER NOT NULL DEFAULT 1,
                        count_voice_when_alone INTEGER NOT NULL DEFAULT 0,
                        max_admin_grant_per_use INTEGER NOT NULL DEFAULT 100000,
                        casino_max_bet INTEGER NOT NULL DEFAULT 1000,
                        casino_daily_profit_limit INTEGER NOT NULL DEFAULT 5000,
                        casino_min_bet_coin_flip INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_dice INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_slot INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_roulette INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_mascot_race INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_duel INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_blackjack INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_scratch_card INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_collective_race INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_match_bet INTEGER NOT NULL DEFAULT 1,
                        casino_min_bet_truco INTEGER NOT NULL DEFAULT 1,
                        casino_limiters_enabled INTEGER NOT NULL DEFAULT 1,
                        savings_daily_interest_bps INTEGER NOT NULL DEFAULT 0,
                        economy_manager_role_id INTEGER,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """)
                self._ensure_column(
                    connection,
                    "guild_settings",
                    "casino_max_bet",
                    "INTEGER NOT NULL DEFAULT 1000",
                )
                self._ensure_column(
                    connection,
                    "guild_settings",
                    "casino_daily_profit_limit",
                    "INTEGER NOT NULL DEFAULT 5000",
                )
                self._ensure_column(
                    connection,
                    "guild_settings",
                    "casino_limiters_enabled",
                    "INTEGER NOT NULL DEFAULT 1",
                )
                self._ensure_column(
                    connection,
                    "guild_settings",
                    "savings_daily_interest_bps",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                for column in (
                    "casino_min_bet_coin_flip",
                    "casino_min_bet_dice",
                    "casino_min_bet_slot",
                    "casino_min_bet_roulette",
                    "casino_min_bet_mascot_race",
                    "casino_min_bet_duel",
                    "casino_min_bet_blackjack",
                    "casino_min_bet_scratch_card",
                    "casino_min_bet_collective_race",
                    "casino_min_bet_match_bet",
                    "casino_min_bet_truco",
                ):
                    self._ensure_column(
                        connection,
                        "guild_settings",
                        column,
                        "INTEGER NOT NULL DEFAULT 1",
                    )
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS user_wallets (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        balance INTEGER NOT NULL DEFAULT 0,
                        total_earned INTEGER NOT NULL DEFAULT 0,
                        total_spent INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS user_savings_accounts (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        balance INTEGER NOT NULL DEFAULT 0,
                        total_interest_earned INTEGER NOT NULL DEFAULT 0,
                        last_interest_at TEXT NOT NULL,
                        locked_until TEXT,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    )
                    """)
                self._ensure_column(
                    connection,
                    "user_savings_accounts",
                    "total_interest_earned",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS activity_claim_cursors (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        claimed_voice_seconds INTEGER NOT NULL DEFAULT 0,
                        claimed_messages INTEGER NOT NULL DEFAULT 0,
                        last_claimed_at TEXT,
                        last_source TEXT,
                        PRIMARY KEY (guild_id, user_id)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS economy_reward_claims (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        reward_key TEXT NOT NULL,
                        last_claimed_at TEXT NOT NULL,
                        last_claim_date TEXT,
                        claim_count INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (guild_id, user_id, reward_key)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS user_credit_protection (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        saves INTEGER NOT NULL DEFAULT 0,
                        lose_streak INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS economy_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        actor_id INTEGER,
                        type TEXT NOT NULL,
                        amount INTEGER NOT NULL,
                        balance_before INTEGER NOT NULL,
                        balance_after INTEGER NOT NULL,
                        reason TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS native_message_stats (
                        guild_id INTEGER NOT NULL,
                        channel_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        message_count INTEGER NOT NULL DEFAULT 0,
                        last_message_at TEXT,
                        PRIMARY KEY (guild_id, channel_id, user_id)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS native_voice_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        channel_id INTEGER NOT NULL,
                        started_at TEXT NOT NULL,
                        ended_at TEXT,
                        duration_seconds INTEGER,
                        is_valid INTEGER NOT NULL DEFAULT 1,
                        invalid_reason TEXT
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS reward_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        type TEXT NOT NULL,
                        price INTEGER NOT NULL,
                        stock_quantity INTEGER,
                        stock_mode TEXT NOT NULL DEFAULT 'LIMITED',
                        max_per_user INTEGER,
                        role_id INTEGER,
                        delivery_message TEXT,
                        duration_days INTEGER,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        deleted_at TEXT
                    )
                    """)
                self._ensure_column(
                    connection,
                    "reward_items",
                    "duration_days",
                    "INTEGER",
                )
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS reward_purchases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        reward_id INTEGER NOT NULL,
                        transaction_id INTEGER,
                        price_paid INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'COMPLETED',
                        delivery_status TEXT NOT NULL DEFAULT 'PENDING',
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        delivered_at TEXT,
                        FOREIGN KEY(reward_id) REFERENCES reward_items(id),
                        FOREIGN KEY(transaction_id) REFERENCES economy_transactions(id)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS reward_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        reward_id INTEGER NOT NULL,
                        code_encrypted TEXT NOT NULL,
                        is_claimed INTEGER NOT NULL DEFAULT 0,
                        claimed_by INTEGER,
                        claimed_at TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(reward_id) REFERENCES reward_items(id)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS shop_level_configs (
                        guild_id INTEGER NOT NULL,
                        level INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        price INTEGER NOT NULL,
                        saves_reward INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, level),
                        UNIQUE(guild_id, role_id)
                    )
                    """)
                self._ensure_column(
                    connection,
                    "shop_level_configs",
                    "saves_reward",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS user_level_upgrades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        level INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        transaction_id INTEGER NOT NULL,
                        price_paid INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(guild_id, level)
                            REFERENCES shop_level_configs(guild_id, level),
                        FOREIGN KEY(transaction_id)
                            REFERENCES economy_transactions(id),
                        UNIQUE(guild_id, user_id, level)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS admin_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        actor_id INTEGER NOT NULL,
                        action TEXT NOT NULL,
                        target_user_id INTEGER,
                        target_resource_id TEXT,
                        before_data_json TEXT NOT NULL DEFAULT '{}',
                        after_data_json TEXT NOT NULL DEFAULT '{}',
                        reason TEXT,
                        created_at TEXT NOT NULL
                    )
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS
                        idx_economy_transactions_guild_user_created
                    ON economy_transactions(guild_id, user_id, created_at DESC)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_economy_reward_claims_user
                    ON economy_reward_claims(guild_id, user_id, reward_key)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_credit_protection_guild
                    ON user_credit_protection(guild_id, user_id)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_savings_accounts_guild
                    ON user_savings_accounts(guild_id, user_id)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_native_voice_sessions_guild_user
                    ON native_voice_sessions(guild_id, user_id, started_at DESC)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_native_voice_sessions_open
                    ON native_voice_sessions(guild_id, user_id, ended_at)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_native_message_stats_guild_user
                    ON native_message_stats(guild_id, user_id)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reward_items_guild_active
                    ON reward_items(guild_id, is_active, price)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reward_purchases_guild_user_created
                    ON reward_purchases(guild_id, user_id, created_at DESC)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reward_purchases_reward_user
                    ON reward_purchases(guild_id, reward_id, user_id)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_shop_level_configs_active
                    ON shop_level_configs(guild_id, is_active, level)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_level_upgrades_user
                    ON user_level_upgrades(guild_id, user_id, level)
                    """)

    def _get_or_create_settings_sync(self, guild_id: int) -> GuildEconomySettings:
        with self._lock:
            with self._connect() as connection:
                row = self._get_settings_row(connection, guild_id)
                if row is None:
                    now = serialize_datetime(utc_now())
                    connection.execute(
                        """
                        INSERT INTO guild_settings (guild_id, created_at, updated_at)
                        VALUES (?, ?, ?)
                        """,
                        (guild_id, now, now),
                    )
                    row = self._get_settings_row(connection, guild_id)
        if row is None:
            raise RuntimeError("Nao foi possivel criar configuracao da guild.")
        return self._row_to_settings(row)

    def _update_guild_settings_sync(
        self,
        guild_id: int,
        updates: dict[str, Any],
    ) -> GuildEconomySettings:
        allowed_columns = {
            "currency_name",
            "voice_points_per_minute",
            "message_points",
            "activity_provider",
            "economy_channel_id",
            "shop_channel_id",
            "staff_log_channel_id",
            "min_voice_seconds_to_claim",
            "min_messages_to_claim",
            "ignore_afk_channel",
            "ignore_bots",
            "count_voice_when_alone",
            "max_admin_grant_per_use",
            "casino_max_bet",
            "casino_daily_profit_limit",
            "casino_min_bet_coin_flip",
            "casino_min_bet_dice",
            "casino_min_bet_slot",
            "casino_min_bet_roulette",
            "casino_min_bet_mascot_race",
            "casino_min_bet_duel",
            "casino_min_bet_blackjack",
            "casino_min_bet_scratch_card",
            "casino_min_bet_collective_race",
            "casino_min_bet_match_bet",
            "casino_min_bet_truco",
            "casino_limiters_enabled",
            "savings_daily_interest_bps",
            "economy_manager_role_id",
        }
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            if key not in allowed_columns:
                continue
            assignments.append(f"{key} = ?")
            params.append(value)

        if not assignments:
            return self._get_or_create_settings_sync(guild_id)

        now = serialize_datetime(utc_now())
        assignments.append("updated_at = ?")
        params.extend([now, guild_id])

        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._ensure_settings(connection, guild_id)
                connection.execute(
                    f"""
                    UPDATE guild_settings
                    SET {", ".join(assignments)}
                    WHERE guild_id = ?
                    """,
                    params,
                )
                connection.commit()

        return self._get_or_create_settings_sync(guild_id)

    def _get_admin_summary_sync(self, guild_id: int) -> dict[str, Any]:
        with self._lock:
            with self._connect() as connection:
                wallet_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS wallet_count,
                        COALESCE(SUM(balance), 0) AS total_balance,
                        COALESCE(SUM(total_earned), 0) AS total_earned,
                        COALESCE(SUM(total_spent), 0) AS total_spent
                    FROM user_wallets
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()
                savings_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS account_count,
                        COALESCE(SUM(balance), 0) AS total_balance,
                        COALESCE(SUM(total_interest_earned), 0)
                            AS total_interest_earned
                    FROM user_savings_accounts
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()
                transaction_rows = connection.execute(
                    """
                    SELECT
                        type,
                        COUNT(*) AS transaction_count,
                        COALESCE(SUM(amount), 0) AS net_amount,
                        COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0)
                            AS total_in,
                        COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0)
                            AS total_out
                    FROM economy_transactions
                    WHERE guild_id = ?
                    GROUP BY type
                    ORDER BY type ASC
                    """,
                    (guild_id,),
                ).fetchall()
                shop_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS rewards_total,
                        COALESCE(SUM(CASE
                            WHEN is_active = 1 AND deleted_at IS NULL THEN 1
                            ELSE 0
                        END), 0) AS rewards_active,
                        COALESCE(SUM(CASE
                            WHEN is_active = 0 AND deleted_at IS NULL THEN 1
                            ELSE 0
                        END), 0) AS rewards_inactive,
                        COALESCE(SUM(CASE
                            WHEN deleted_at IS NOT NULL THEN 1
                            ELSE 0
                        END), 0) AS rewards_removed
                    FROM reward_items
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()
                purchase_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS purchase_count,
                        COALESCE(SUM(price_paid), 0) AS purchase_volume
                    FROM reward_purchases
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()
                audit_row = connection.execute(
                    """
                    SELECT COUNT(*) AS audit_count
                    FROM admin_audit_logs
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()
                activity_row = connection.execute(
                    """
                    SELECT
                        COALESCE(SUM(message_count), 0) AS total_messages,
                        COUNT(DISTINCT user_id) AS message_users
                    FROM native_message_stats
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()
                voice_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS voice_sessions,
                        COALESCE(SUM(COALESCE(duration_seconds, 0)), 0)
                            AS voice_seconds
                    FROM native_voice_sessions
                    WHERE guild_id = ?
                      AND is_valid = 1
                    """,
                    (guild_id,),
                ).fetchone()

        transactions = {
            str(row["type"]): {
                "count": int(row["transaction_count"] or 0),
                "net": int(row["net_amount"] or 0),
                "in": int(row["total_in"] or 0),
                "out": int(row["total_out"] or 0),
            }
            for row in transaction_rows
        }
        return {
            "wallets": {
                "count": int(wallet_row["wallet_count"] or 0),
                "balance": int(wallet_row["total_balance"] or 0),
                "earned": int(wallet_row["total_earned"] or 0),
                "spent": int(wallet_row["total_spent"] or 0),
            },
            "savings": {
                "count": int(savings_row["account_count"] or 0),
                "balance": int(savings_row["total_balance"] or 0),
                "interest_earned": int(savings_row["total_interest_earned"] or 0),
            },
            "transactions": transactions,
            "shop": {
                "rewards_total": int(shop_row["rewards_total"] or 0),
                "rewards_active": int(shop_row["rewards_active"] or 0),
                "rewards_inactive": int(shop_row["rewards_inactive"] or 0),
                "rewards_removed": int(shop_row["rewards_removed"] or 0),
                "purchase_count": int(purchase_row["purchase_count"] or 0),
                "purchase_volume": int(purchase_row["purchase_volume"] or 0),
            },
            "audit": {
                "count": int(audit_row["audit_count"] or 0),
            },
            "activity": {
                "messages": int(activity_row["total_messages"] or 0),
                "message_users": int(activity_row["message_users"] or 0),
                "voice_sessions": int(voice_row["voice_sessions"] or 0),
                "voice_seconds": int(voice_row["voice_seconds"] or 0),
            },
        }

    def _reset_user_profile_sync(
        self,
        guild_id: int,
        user_id: int,
    ) -> UserProfileResetResult:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                wallet_row = self._get_wallet_row(connection, guild_id, user_id)
                wallet_before = (
                    self._row_to_wallet(wallet_row) if wallet_row is not None else None
                )

                deleted_purchases = connection.execute(
                    """
                    DELETE FROM reward_purchases
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_level_upgrades = connection.execute(
                    """
                    DELETE FROM user_level_upgrades
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_credit_protection = connection.execute(
                    """
                    DELETE FROM user_credit_protection
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_savings_accounts = connection.execute(
                    """
                    DELETE FROM user_savings_accounts
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_reward_claims = connection.execute(
                    """
                    DELETE FROM economy_reward_claims
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_activity_cursors = connection.execute(
                    """
                    DELETE FROM activity_claim_cursors
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_message_stats = connection.execute(
                    """
                    DELETE FROM native_message_stats
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_voice_sessions = connection.execute(
                    """
                    DELETE FROM native_voice_sessions
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_transactions = connection.execute(
                    """
                    DELETE FROM economy_transactions
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_wallets = connection.execute(
                    """
                    DELETE FROM user_wallets
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                connection.commit()

        return UserProfileResetResult(
            wallet_before=wallet_before,
            deleted_transactions=max(0, deleted_transactions),
            deleted_reward_claims=max(0, deleted_reward_claims),
            deleted_activity_cursors=max(0, deleted_activity_cursors),
            deleted_message_stats=max(0, deleted_message_stats),
            deleted_voice_sessions=max(0, deleted_voice_sessions),
            deleted_purchases=max(0, deleted_purchases),
            deleted_wallets=max(0, deleted_wallets),
            deleted_level_upgrades=max(0, deleted_level_upgrades),
            deleted_credit_protection=max(0, deleted_credit_protection),
            deleted_savings_accounts=max(0, deleted_savings_accounts),
        )

    def _get_or_create_wallet_sync(self, guild_id: int, user_id: int) -> UserWallet:
        with self._lock:
            with self._connect() as connection:
                row = self._ensure_wallet(connection, guild_id, user_id)
        return self._row_to_wallet(row)

    def _get_or_create_credit_protection_state_sync(
        self,
        guild_id: int,
        user_id: int,
    ) -> CreditProtectionState:
        with self._lock:
            with self._connect() as connection:
                row = self._ensure_credit_protection_state(
                    connection,
                    guild_id,
                    user_id,
                )
        return self._row_to_credit_protection_state(row)

    def _adjust_credit_saves_sync(
        self,
        guild_id: int,
        user_id: int,
        delta: int,
    ) -> CreditProtectionAdjustmentResult:
        if delta == 0:
            raise ValueError("A quantidade de saves precisa ser diferente de zero.")

        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                before_row = self._ensure_credit_protection_state(
                    connection,
                    guild_id,
                    user_id,
                )
                before = self._row_to_credit_protection_state(before_row)
                saves_after = before.saves + delta
                if saves_after < 0:
                    connection.rollback()
                    raise ValueError("O usuario nao possui saves suficientes.")

                now = serialize_datetime(utc_now())
                connection.execute(
                    """
                    UPDATE user_credit_protection
                    SET saves = ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (saves_after, now, guild_id, user_id),
                )
                after_row = self._get_credit_protection_row(
                    connection,
                    guild_id,
                    user_id,
                )
                connection.commit()

        if after_row is None:
            raise RuntimeError("Nao foi possivel recuperar os saves do usuario.")
        return CreditProtectionAdjustmentResult(
            before=before,
            after=self._row_to_credit_protection_state(after_row),
            delta=delta,
        )

    def _apply_credit_protection_sync(
        self,
        guild_id: int,
        user_id: int,
        game_key: str,
        stake: int,
        is_loss: bool,
        metadata: dict[str, Any],
    ) -> CreditProtectionResult:
        if stake <= 0:
            return CreditProtectionResult(
                state=self._get_or_create_credit_protection_state_sync(
                    guild_id,
                    user_id,
                )
            )

        normalized_game_key = (game_key or "game").strip()[:64] or "game"
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                state_row = self._ensure_credit_protection_state(
                    connection,
                    guild_id,
                    user_id,
                )
                saves = int(state_row["saves"])
                lose_streak_before = int(state_row["lose_streak"])
                now = serialize_datetime(utc_now())
                transaction: EconomyTransaction | None = None
                wallet: UserWallet | None = None
                cashback_amount = 0
                cashback_percent = 0
                save_consumed = False

                if not is_loss:
                    connection.execute(
                        """
                        UPDATE user_credit_protection
                        SET lose_streak = 0,
                            updated_at = ?
                        WHERE guild_id = ? AND user_id = ?
                        """,
                        (now, guild_id, user_id),
                    )
                    triggered_streak = 0
                else:
                    triggered_streak = lose_streak_before + 1
                    if (
                        saves > 0
                        and triggered_streak >= self.CREDIT_CASHBACK_HIGH_STREAK
                    ):
                        cashback_percent = self.CREDIT_CASHBACK_HIGH_PERCENT
                    elif (
                        saves > 0
                        and triggered_streak >= self.CREDIT_CASHBACK_LOW_STREAK
                    ):
                        cashback_percent = self.CREDIT_CASHBACK_LOW_PERCENT

                    if cashback_percent:
                        cashback_amount = max(1, (stake * cashback_percent) // 100)
                        saves -= 1
                        save_consumed = True
                        wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                        balance_before = int(wallet_row["balance"])
                        balance_after = balance_before + cashback_amount
                        connection.execute(
                            """
                            UPDATE user_wallets
                            SET balance = ?,
                                total_earned = total_earned + ?,
                                updated_at = ?
                            WHERE guild_id = ? AND user_id = ?
                            """,
                            (
                                balance_after,
                                cashback_amount,
                                now,
                                guild_id,
                                user_id,
                            ),
                        )
                        transaction = self._insert_transaction(
                            connection,
                            guild_id=guild_id,
                            user_id=user_id,
                            actor_id=None,
                            transaction_type=EconomyTransactionType.CREDIT_CASHBACK,
                            amount=cashback_amount,
                            balance_before=balance_before,
                            balance_after=balance_after,
                            reason="credit_protection_cashback",
                            metadata={
                                **metadata,
                                "game": normalized_game_key,
                                "stake": stake,
                                "cashback_percent": cashback_percent,
                                "lose_streak": triggered_streak,
                                "save_consumed": True,
                            },
                            created_at=now,
                        )

                    connection.execute(
                        """
                        UPDATE user_credit_protection
                        SET saves = ?,
                            lose_streak = ?,
                            updated_at = ?
                        WHERE guild_id = ? AND user_id = ?
                        """,
                        (saves, triggered_streak, now, guild_id, user_id),
                    )

                final_row = self._get_credit_protection_row(
                    connection,
                    guild_id,
                    user_id,
                )
                if cashback_amount > 0:
                    wallet_row = self._get_wallet_row(connection, guild_id, user_id)
                    wallet = self._row_to_wallet(wallet_row)
                connection.commit()

        if final_row is None:
            raise RuntimeError("Nao foi possivel recuperar a protecao de credito.")
        return CreditProtectionResult(
            state=self._row_to_credit_protection_state(final_row),
            wallet=wallet,
            transaction=transaction,
            cashback_amount=cashback_amount,
            cashback_percent=cashback_percent,
            save_consumed=save_consumed,
            triggered_streak=triggered_streak,
        )

    def _get_savings_overview_sync(
        self,
        guild_id: int,
        user_id: int,
        daily_interest_bps: int,
    ) -> SavingsOverview:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                account_row = self._ensure_savings_account(
                    connection,
                    guild_id,
                    user_id,
                )
                interest_applied = self._apply_savings_interest(
                    connection,
                    account_row,
                    daily_interest_bps,
                )
                account_row = self._get_savings_account_row(
                    connection,
                    guild_id,
                    user_id,
                )
                connection.commit()

        if account_row is None:
            raise RuntimeError("Não foi possível recuperar a poupança.")
        return self._build_savings_overview(
            wallet_row,
            account_row,
            daily_interest_bps,
            interest_applied,
        )

    def _deposit_savings_sync(
        self,
        guild_id: int,
        user_id: int,
        amount: int,
        daily_interest_bps: int,
    ) -> SavingsOperationResult:
        if amount <= 0:
            raise ValueError("O valor do depósito precisa ser maior que zero.")

        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                account_row = self._ensure_savings_account(
                    connection,
                    guild_id,
                    user_id,
                )
                interest_applied = self._apply_savings_interest(
                    connection,
                    account_row,
                    daily_interest_bps,
                )
                account_row = self._get_savings_account_row(
                    connection,
                    guild_id,
                    user_id,
                )
                if account_row is None:
                    connection.rollback()
                    raise RuntimeError("Não foi possível recuperar a poupança.")

                balance_before = int(wallet_row["balance"])
                max_deposit = self._calculate_max_savings_deposit(balance_before)
                if amount > max_deposit:
                    connection.rollback()
                    raise ValueError(
                        "Você pode depositar no máximo 70% do saldo em caixa. "
                        f"Limite atual: {max_deposit}."
                    )
                if amount > balance_before:
                    connection.rollback()
                    raise ValueError("Saldo insuficiente para esse depósito.")

                now_dt = utc_now()
                now = serialize_datetime(now_dt)
                locked_until = serialize_datetime(
                    now_dt + timedelta(days=self.SAVINGS_LOCK_DAYS)
                )
                balance_after = balance_before - amount
                savings_after = int(account_row["balance"]) + amount
                connection.execute(
                    """
                    UPDATE user_wallets
                    SET balance = ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (balance_after, now, guild_id, user_id),
                )
                connection.execute(
                    """
                    UPDATE user_savings_accounts
                    SET balance = ?,
                        last_interest_at = ?,
                        locked_until = ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (
                        savings_after,
                        now,
                        locked_until,
                        now,
                        guild_id,
                        user_id,
                    ),
                )
                transaction = self._insert_transaction(
                    connection,
                    guild_id=guild_id,
                    user_id=user_id,
                    actor_id=user_id,
                    transaction_type=EconomyTransactionType.SAVINGS_DEPOSIT,
                    amount=-amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    reason="savings_deposit",
                    metadata={
                        "interest_applied": interest_applied,
                        "locked_until": locked_until,
                        "max_deposit_percent": self.SAVINGS_MAX_DEPOSIT_PERCENT,
                    },
                    created_at=now,
                )
                wallet_row = self._get_wallet_row(connection, guild_id, user_id)
                account_row = self._get_savings_account_row(
                    connection,
                    guild_id,
                    user_id,
                )
                connection.commit()

        if wallet_row is None or account_row is None:
            raise RuntimeError("Não foi possível recuperar a poupança.")
        overview = self._build_savings_overview(
            wallet_row,
            account_row,
            daily_interest_bps,
            interest_applied,
        )
        return SavingsOperationResult(
            overview=overview,
            transaction=transaction,
            amount=amount,
            interest_applied=interest_applied,
        )

    def _withdraw_savings_sync(
        self,
        guild_id: int,
        user_id: int,
        amount: int,
        daily_interest_bps: int,
    ) -> SavingsOperationResult:
        if amount <= 0:
            raise ValueError("O valor do saque precisa ser maior que zero.")

        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                account_row = self._ensure_savings_account(
                    connection,
                    guild_id,
                    user_id,
                )
                interest_applied = self._apply_savings_interest(
                    connection,
                    account_row,
                    daily_interest_bps,
                )
                account_row = self._get_savings_account_row(
                    connection,
                    guild_id,
                    user_id,
                )
                if account_row is None:
                    connection.rollback()
                    raise RuntimeError("Não foi possível recuperar a poupança.")

                locked_until_raw = account_row["locked_until"]
                if locked_until_raw is not None:
                    locked_until = parse_datetime(str(locked_until_raw))
                    now_dt = utc_now()
                    if locked_until > now_dt:
                        locked_until_label = locked_until.strftime(
                            "%d/%m/%Y às %H:%M UTC"
                        )
                        connection.rollback()
                        raise ValueError(
                            "Sua poupança ainda está bloqueada até "
                            f"{locked_until_label}."
                        )
                else:
                    now_dt = utc_now()

                savings_before = int(account_row["balance"])
                if amount > savings_before:
                    connection.rollback()
                    raise ValueError("Saldo insuficiente na poupança.")

                now = serialize_datetime(now_dt)
                wallet_before = int(wallet_row["balance"])
                wallet_after = wallet_before + amount
                savings_after = savings_before - amount
                next_locked_until = None if savings_after == 0 else locked_until_raw
                connection.execute(
                    """
                    UPDATE user_wallets
                    SET balance = ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (wallet_after, now, guild_id, user_id),
                )
                connection.execute(
                    """
                    UPDATE user_savings_accounts
                    SET balance = ?,
                        last_interest_at = ?,
                        locked_until = ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (
                        savings_after,
                        now,
                        next_locked_until,
                        now,
                        guild_id,
                        user_id,
                    ),
                )
                transaction = self._insert_transaction(
                    connection,
                    guild_id=guild_id,
                    user_id=user_id,
                    actor_id=user_id,
                    transaction_type=EconomyTransactionType.SAVINGS_WITHDRAW,
                    amount=amount,
                    balance_before=wallet_before,
                    balance_after=wallet_after,
                    reason="savings_withdraw",
                    metadata={"interest_applied": interest_applied},
                    created_at=now,
                )
                wallet_row = self._get_wallet_row(connection, guild_id, user_id)
                account_row = self._get_savings_account_row(
                    connection,
                    guild_id,
                    user_id,
                )
                connection.commit()

        if wallet_row is None or account_row is None:
            raise RuntimeError("Não foi possível recuperar a poupança.")
        overview = self._build_savings_overview(
            wallet_row,
            account_row,
            daily_interest_bps,
            interest_applied,
        )
        return SavingsOperationResult(
            overview=overview,
            transaction=transaction,
            amount=amount,
            interest_applied=interest_applied,
        )

    def _mutate_balance_sync(
        self,
        guild_id: int,
        user_id: int,
        amount: int,
        transaction_type: EconomyTransactionType,
        actor_id: int | None,
        reason: str | None,
        metadata: dict[str, Any],
    ) -> BalanceMutationResult:
        if amount == 0:
            raise ValueError("A quantidade de pontos nao pode ser zero.")

        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                balance_before = int(wallet_row["balance"])
                balance_after = balance_before + amount
                if balance_after < 0:
                    connection.rollback()
                    raise ValueError("Saldo insuficiente.")

                now = serialize_datetime(utc_now())
                total_earned_delta = max(amount, 0)
                total_spent_delta = abs(min(amount, 0))
                connection.execute(
                    """
                    UPDATE user_wallets
                    SET balance = ?,
                        total_earned = total_earned + ?,
                        total_spent = total_spent + ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (
                        balance_after,
                        total_earned_delta,
                        total_spent_delta,
                        now,
                        guild_id,
                        user_id,
                    ),
                )
                transaction = self._insert_transaction(
                    connection,
                    guild_id=guild_id,
                    user_id=user_id,
                    actor_id=actor_id,
                    transaction_type=transaction_type,
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    reason=reason,
                    metadata=metadata,
                    created_at=now,
                )
                connection.commit()

        wallet = self._get_or_create_wallet_sync(guild_id, user_id)
        return BalanceMutationResult(wallet=wallet, transaction=transaction)

    def _grant_achievement_reward_once_sync(
        self,
        guild_id: int,
        user_id: int,
        achievement_key: str,
        amount: int,
    ) -> BalanceMutationResult | None:
        if amount <= 0:
            return None

        reward_key = f"achievement:{achievement_key}"
        now = serialize_datetime(utc_now())

        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                claim_row = self._get_reward_claim_row(
                    connection,
                    guild_id,
                    user_id,
                    reward_key,
                )
                if claim_row is not None and int(claim_row["claim_count"]) > 0:
                    connection.rollback()
                    return None

                if self._has_achievement_reward_transaction(
                    connection,
                    guild_id,
                    user_id,
                    achievement_key,
                ):
                    self._upsert_reward_claim(
                        connection,
                        guild_id=guild_id,
                        user_id=user_id,
                        reward_key=reward_key,
                        claim_date=None,
                        now=now,
                    )
                    connection.commit()
                    return None

                wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                balance_before = int(wallet_row["balance"])
                balance_after = balance_before + amount
                connection.execute(
                    """
                    UPDATE user_wallets
                    SET balance = ?,
                        total_earned = total_earned + ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (balance_after, amount, now, guild_id, user_id),
                )
                transaction = self._insert_transaction(
                    connection,
                    guild_id=guild_id,
                    user_id=user_id,
                    actor_id=None,
                    transaction_type=EconomyTransactionType.SYSTEM_ADJUSTMENT,
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    reason="achievement_reward",
                    metadata={"achievement_key": achievement_key},
                    created_at=now,
                )
                self._upsert_reward_claim(
                    connection,
                    guild_id=guild_id,
                    user_id=user_id,
                    reward_key=reward_key,
                    claim_date=None,
                    now=now,
                )
                connection.commit()

        wallet = self._get_or_create_wallet_sync(guild_id, user_id)
        return BalanceMutationResult(wallet=wallet, transaction=transaction)

    def _transfer_balance_sync(
        self,
        guild_id: int,
        sender_id: int,
        receiver_id: int,
        amount: int,
        reason: str,
        metadata: dict[str, Any],
    ) -> UserTransferResult:
        if amount <= 0:
            raise ValueError("A quantidade precisa ser maior que zero.")
        if sender_id == receiver_id:
            raise ValueError("Voce nao pode transferir pontos para si mesmo.")

        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                sender_row = self._ensure_wallet(connection, guild_id, sender_id)
                receiver_row = self._ensure_wallet(connection, guild_id, receiver_id)
                sender_balance_before = int(sender_row["balance"])
                receiver_balance_before = int(receiver_row["balance"])
                if sender_balance_before < amount:
                    connection.rollback()
                    raise ValueError("Saldo insuficiente para essa transferencia.")

                now = serialize_datetime(utc_now())
                sender_balance_after = sender_balance_before - amount
                receiver_balance_after = receiver_balance_before + amount
                connection.execute(
                    """
                    UPDATE user_wallets
                    SET balance = ?,
                        total_spent = total_spent + ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (sender_balance_after, amount, now, guild_id, sender_id),
                )
                connection.execute(
                    """
                    UPDATE user_wallets
                    SET balance = ?,
                        total_earned = total_earned + ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (receiver_balance_after, amount, now, guild_id, receiver_id),
                )
                sender_transaction = self._insert_transaction(
                    connection,
                    guild_id=guild_id,
                    user_id=sender_id,
                    actor_id=sender_id,
                    transaction_type=EconomyTransactionType.USER_TRANSFER,
                    amount=-amount,
                    balance_before=sender_balance_before,
                    balance_after=sender_balance_after,
                    reason=reason,
                    metadata={
                        **metadata,
                        "direction": "sent",
                        "receiver_id": receiver_id,
                    },
                    created_at=now,
                )
                receiver_transaction = self._insert_transaction(
                    connection,
                    guild_id=guild_id,
                    user_id=receiver_id,
                    actor_id=sender_id,
                    transaction_type=EconomyTransactionType.USER_TRANSFER,
                    amount=amount,
                    balance_before=receiver_balance_before,
                    balance_after=receiver_balance_after,
                    reason=reason,
                    metadata={
                        **metadata,
                        "direction": "received",
                        "sender_id": sender_id,
                    },
                    created_at=now,
                )
                connection.commit()

        return UserTransferResult(
            sender_wallet=self._get_or_create_wallet_sync(guild_id, sender_id),
            receiver_wallet=self._get_or_create_wallet_sync(guild_id, receiver_id),
            sender_transaction=sender_transaction,
            receiver_transaction=receiver_transaction,
            amount=amount,
        )

    def _list_transactions_sync(
        self,
        guild_id: int,
        user_id: int,
        limit: int,
    ) -> list[EconomyTransaction]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM economy_transactions
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (guild_id, user_id, max(1, min(limit, 50))),
                ).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def _get_user_casino_profit_since_sync(
        self,
        guild_id: int,
        user_id: int,
        since: str,
    ) -> int:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT COALESCE(SUM(amount), 0) AS net_profit
                    FROM economy_transactions
                    WHERE guild_id = ?
                      AND user_id = ?
                      AND created_at >= ?
                      AND type IN (
                          'CASINO_BET',
                          'CASINO_PAYOUT',
                          'MATCH_BET',
                          'MATCH_BET_PAYOUT',
                          'REFUND',
                          'CREDIT_CASHBACK'
                      )
                    """,
                    (guild_id, user_id, since),
                ).fetchone()
        return int(row["net_profit"] or 0)

    def _count_user_scratch_card_purchases_since_sync(
        self,
        guild_id: int,
        user_id: int,
        since: str,
    ) -> int:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT COUNT(*) AS purchase_count
                    FROM economy_transactions
                    WHERE guild_id = ?
                      AND user_id = ?
                      AND created_at >= ?
                      AND type = 'CASINO_BET'
                      AND reason = 'scratch_card_bet'
                    """,
                    (guild_id, user_id, since),
                ).fetchone()
        return int(row["purchase_count"] or 0)

    def _list_casino_transactions_sync(
        self,
        guild_id: int,
        limit: int,
    ) -> list[EconomyTransaction]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM economy_transactions
                    WHERE guild_id = ?
                      AND type IN (
                          'CASINO_BET',
                          'CASINO_PAYOUT',
                          'MATCH_BET',
                          'MATCH_BET_PAYOUT',
                          'REFUND',
                          'CREDIT_CASHBACK'
                      )
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (guild_id, max(1, min(limit, 1000))),
                ).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def _get_user_game_progress_summary_sync(
        self,
        guild_id: int,
        user_id: int,
    ) -> UserGameProgressSummary:
        with self._lock:
            with self._connect() as connection:
                wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                rows = connection.execute(
                    """
                    SELECT *
                    FROM economy_transactions
                    WHERE guild_id = ?
                      AND user_id = ?
                      AND type IN (
                          'CASINO_BET',
                          'CASINO_PAYOUT',
                          'REFUND',
                          'CREDIT_CASHBACK'
                      )
                    ORDER BY created_at ASC, id ASC
                    """,
                    (guild_id, user_id),
                ).fetchall()

        transactions = [self._row_to_transaction(row) for row in rows]
        total_games_played = 0
        total_wins = 0
        total_wagered = 0
        total_payout = 0
        net_profit = 0
        biggest_win = 0
        duel_games = 0
        duel_wins = 0
        collective_race_wins = 0
        scratch_plays = 0
        scratch_wins = 0
        blackjack_best_streak = 0

        for transaction in transactions:
            game = str(transaction.metadata.get("game") or "")
            if transaction.type is EconomyTransactionType.CASINO_BET:
                amount = abs(transaction.amount)
                total_wagered += amount
                net_profit += transaction.amount
                if transaction.reason != "blackjack_double":
                    total_games_played += 1
                if game == "duel":
                    duel_games += 1
                elif game == "scratch_card":
                    scratch_plays += 1
                continue

            if transaction.type in {
                EconomyTransactionType.REFUND,
                EconomyTransactionType.CREDIT_CASHBACK,
            }:
                net_profit += transaction.amount
                continue

            if transaction.type is not EconomyTransactionType.CASINO_PAYOUT:
                continue

            payout = max(transaction.amount, 0)
            total_payout += payout
            net_profit += transaction.amount
            if payout <= 0:
                continue

            outcome = str(transaction.metadata.get("outcome") or "")
            is_winning_payout = outcome in {
                "PLAYER_BLACKJACK",
                "PLAYER_WIN",
                "WON",
            } or (not outcome and game in {"collective_race", "scratch_card"})
            if not is_winning_payout:
                continue

            total_wins += 1
            biggest_win = max(biggest_win, payout)
            if game == "duel":
                duel_wins += 1
            elif game == "collective_race":
                collective_race_wins += 1
            elif game == "scratch_card":
                scratch_wins += 1

            raw_streak = transaction.metadata.get("win_streak")
            if raw_streak is not None:
                try:
                    blackjack_best_streak = max(blackjack_best_streak, int(raw_streak))
                except (TypeError, ValueError):
                    pass

        return UserGameProgressSummary(
            wallet=self._row_to_wallet(wallet_row),
            total_games_played=total_games_played,
            total_wins=total_wins,
            total_wagered=total_wagered,
            total_payout=total_payout,
            net_profit=net_profit,
            biggest_win=biggest_win,
            duel_games=duel_games,
            duel_wins=duel_wins,
            collective_race_wins=collective_race_wins,
            scratch_plays=scratch_plays,
            scratch_wins=scratch_wins,
            blackjack_best_streak=blackjack_best_streak,
        )

    def _list_top_wallets_sync(self, guild_id: int, limit: int) -> list[UserWallet]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM user_wallets
                    WHERE guild_id = ?
                    ORDER BY balance DESC, total_earned DESC, user_id ASC
                    LIMIT ?
                    """,
                    (guild_id, max(1, min(limit, 50))),
                ).fetchall()
        return [self._row_to_wallet(row) for row in rows]

    def _record_audit_log_sync(
        self,
        guild_id: int,
        actor_id: int,
        action: str,
        target_user_id: int | None,
        target_resource_id: str | None,
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        reason: str | None,
    ) -> AdminAuditLog:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO admin_audit_logs (
                        guild_id,
                        actor_id,
                        action,
                        target_user_id,
                        target_resource_id,
                        before_data_json,
                        after_data_json,
                        reason,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        actor_id,
                        action,
                        target_user_id,
                        target_resource_id,
                        json.dumps(before_data, ensure_ascii=True),
                        json.dumps(after_data, ensure_ascii=True),
                        reason,
                        now,
                    ),
                )
        return AdminAuditLog(
            id=int(cursor.lastrowid),
            guild_id=guild_id,
            actor_id=actor_id,
            action=action,
            target_user_id=target_user_id,
            target_resource_id=target_resource_id,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
            created_at=parse_datetime(now),
        )

    def _try_claim_reward_sync(
        self,
        guild_id: int,
        user_id: int,
        reward_key: str,
        claim_date: str | None,
        once: bool,
    ) -> bool:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT last_claim_date, claim_count
                    FROM economy_reward_claims
                    WHERE guild_id = ?
                      AND user_id = ?
                      AND reward_key = ?
                    """,
                    (guild_id, user_id, reward_key),
                ).fetchone()

                if row is not None:
                    claim_count = int(row["claim_count"])
                    if once and claim_count > 0:
                        connection.rollback()
                        return False
                    if not once and row["last_claim_date"] == claim_date:
                        connection.rollback()
                        return False
                    self._update_reward_claim(
                        connection,
                        guild_id=guild_id,
                        user_id=user_id,
                        reward_key=reward_key,
                        claim_date=claim_date,
                        claim_count=claim_count + 1,
                        now=now,
                    )
                else:
                    self._insert_reward_claim(
                        connection,
                        guild_id=guild_id,
                        user_id=user_id,
                        reward_key=reward_key,
                        claim_date=claim_date,
                        now=now,
                    )
                connection.commit()
        return True

    def _record_message_activity_sync(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
    ) -> None:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO native_message_stats (
                        guild_id,
                        channel_id,
                        user_id,
                        message_count,
                        last_message_at
                    ) VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(guild_id, channel_id, user_id) DO UPDATE SET
                        message_count = message_count + 1,
                        last_message_at = excluded.last_message_at
                    """,
                    (guild_id, channel_id, user_id, now),
                )

    def _start_voice_session_sync(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
    ) -> NativeVoiceSession:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM native_voice_sessions
                    WHERE guild_id = ?
                      AND user_id = ?
                      AND ended_at IS NULL
                    ORDER BY started_at DESC, id DESC
                    LIMIT 1
                    """,
                    (guild_id, user_id),
                ).fetchone()
                if row is not None and int(row["channel_id"]) == channel_id:
                    return self._row_to_voice_session(row)

            self._close_voice_sessions_sync(guild_id, user_id, None)
            with self._connect() as connection:
                now = serialize_datetime(utc_now())
                cursor = connection.execute(
                    """
                    INSERT INTO native_voice_sessions (
                        guild_id,
                        user_id,
                        channel_id,
                        started_at,
                        is_valid
                    ) VALUES (?, ?, ?, ?, 1)
                    """,
                    (guild_id, user_id, channel_id, now),
                )
                row = connection.execute(
                    """
                    SELECT *
                    FROM native_voice_sessions
                    WHERE id = ?
                    """,
                    (int(cursor.lastrowid),),
                ).fetchone()
        return self._row_to_voice_session(row)

    def _close_voice_sessions_sync(
        self,
        guild_id: int,
        user_id: int,
        invalid_reason: str | None,
    ) -> list[NativeVoiceSession]:
        closed: list[NativeVoiceSession] = []
        ended_at = utc_now()
        ended_raw = serialize_datetime(ended_at)
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM native_voice_sessions
                    WHERE guild_id = ?
                      AND user_id = ?
                      AND ended_at IS NULL
                    """,
                    (guild_id, user_id),
                ).fetchall()
                for row in rows:
                    started_at = parse_datetime(str(row["started_at"]))
                    elapsed_seconds = int((ended_at - started_at).total_seconds())
                    duration_seconds = max(0, elapsed_seconds)
                    is_valid = 0 if invalid_reason else 1
                    connection.execute(
                        """
                        UPDATE native_voice_sessions
                        SET ended_at = ?,
                            duration_seconds = ?,
                            is_valid = ?,
                            invalid_reason = ?
                        WHERE id = ?
                        """,
                        (
                            ended_raw,
                            duration_seconds,
                            is_valid,
                            invalid_reason,
                            int(row["id"]),
                        ),
                    )
                    closed.append(
                        NativeVoiceSession(
                            id=int(row["id"]),
                            guild_id=guild_id,
                            user_id=user_id,
                            channel_id=int(row["channel_id"]),
                            started_at=started_at,
                            ended_at=ended_at,
                            duration_seconds=duration_seconds,
                            is_valid=bool(is_valid),
                            invalid_reason=invalid_reason,
                        )
                    )
        return closed

    def _get_activity_stats_sync(self, guild_id: int, user_id: int) -> ActivityStats:
        now = utc_now()
        with self._lock:
            with self._connect() as connection:
                messages_row = connection.execute(
                    """
                    SELECT COALESCE(SUM(message_count), 0) AS total_messages
                    FROM native_message_stats
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).fetchone()
                voice_rows = connection.execute(
                    """
                    SELECT started_at, duration_seconds, is_valid
                    FROM native_voice_sessions
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).fetchall()

        total_voice_seconds = 0
        for row in voice_rows:
            if not bool(row["is_valid"]):
                continue
            if row["duration_seconds"] is not None:
                total_voice_seconds += int(row["duration_seconds"])
                continue
            started_at = parse_datetime(str(row["started_at"]))
            total_voice_seconds += max(0, int((now - started_at).total_seconds()))

        return ActivityStats(
            guild_id=guild_id,
            user_id=user_id,
            total_voice_seconds=total_voice_seconds,
            total_messages=int(messages_row["total_messages"] or 0),
            source="native",
            fetched_at=now,
        )

    def _convert_activity_sync(
        self,
        stats: ActivityStats,
        actor_id: int,
    ) -> ActivityConversionResult:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                settings = self._row_to_settings(
                    self._ensure_settings(connection, stats.guild_id)
                )
                wallet_row = self._ensure_wallet(
                    connection,
                    stats.guild_id,
                    stats.user_id,
                )
                cursor = self._row_to_cursor(
                    self._ensure_cursor(connection, stats.guild_id, stats.user_id)
                )

                raw_voice_delta = max(
                    0,
                    stats.total_voice_seconds - cursor.claimed_voice_seconds,
                )
                messages_delta = stats.total_messages - cursor.claimed_messages
                raw_messages_delta = max(0, messages_delta)
                converted_voice_seconds = 0
                if raw_voice_delta >= settings.min_voice_seconds_to_claim:
                    converted_voice_seconds = (raw_voice_delta // 60) * 60
                converted_messages = (
                    raw_messages_delta
                    if raw_messages_delta >= settings.min_messages_to_claim
                    else 0
                )
                voice_points = (
                    converted_voice_seconds // 60
                ) * settings.voice_points_per_minute
                message_points = converted_messages * settings.message_points
                total_points = voice_points + message_points

                transaction: EconomyTransaction | None = None
                now = serialize_datetime(utc_now())
                if total_points > 0:
                    balance_before = int(wallet_row["balance"])
                    balance_after = balance_before + total_points
                    connection.execute(
                        """
                        UPDATE user_wallets
                        SET balance = ?,
                            total_earned = total_earned + ?,
                            updated_at = ?
                        WHERE guild_id = ? AND user_id = ?
                        """,
                        (
                            balance_after,
                            total_points,
                            now,
                            stats.guild_id,
                            stats.user_id,
                        ),
                    )
                    transaction = self._insert_transaction(
                        connection,
                        guild_id=stats.guild_id,
                        user_id=stats.user_id,
                        actor_id=actor_id,
                        transaction_type=EconomyTransactionType.ACTIVITY_CONVERSION,
                        amount=total_points,
                        balance_before=balance_before,
                        balance_after=balance_after,
                        reason="activity_conversion",
                        metadata={
                            "voice_seconds": converted_voice_seconds,
                            "messages": converted_messages,
                            "voice_points": voice_points,
                            "message_points": message_points,
                            "source": stats.source,
                        },
                        created_at=now,
                    )
                    connection.execute(
                        """
                        INSERT INTO activity_claim_cursors (
                            guild_id,
                            user_id,
                            claimed_voice_seconds,
                            claimed_messages,
                            last_claimed_at,
                            last_source
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(guild_id, user_id) DO UPDATE SET
                            claimed_voice_seconds = excluded.claimed_voice_seconds,
                            claimed_messages = excluded.claimed_messages,
                            last_claimed_at = excluded.last_claimed_at,
                            last_source = excluded.last_source
                        """,
                        (
                            stats.guild_id,
                            stats.user_id,
                            cursor.claimed_voice_seconds + converted_voice_seconds,
                            cursor.claimed_messages + converted_messages,
                            now,
                            stats.source,
                        ),
                    )
                connection.commit()

        wallet = self._get_or_create_wallet_sync(stats.guild_id, stats.user_id)
        return ActivityConversionResult(
            wallet=wallet,
            transaction=transaction,
            voice_seconds_delta=converted_voice_seconds,
            messages_delta=converted_messages,
            voice_points=voice_points,
            message_points=message_points,
            total_points=total_points,
            source=stats.source,
        )

    def _create_reward_sync(self, reward: RewardItemCreate) -> RewardItem:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO reward_items (
                        guild_id,
                        name,
                        description,
                        type,
                        price,
                        stock_quantity,
                        stock_mode,
                        max_per_user,
                        role_id,
                        delivery_message,
                        duration_days,
                        is_active,
                        created_by,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        reward.guild_id,
                        reward.name,
                        reward.description,
                        reward.type.value,
                        reward.price,
                        reward.stock_quantity,
                        reward.stock_mode.value,
                        reward.max_per_user,
                        reward.role_id,
                        reward.delivery_message,
                        reward.duration_days,
                        reward.created_by,
                        now,
                        now,
                    ),
                )
        created = self._get_reward_sync(int(cursor.lastrowid))
        if created is None:
            raise RuntimeError("Nao foi possivel criar recompensa.")
        return created

    def _list_rewards_sync(
        self,
        guild_id: int,
        include_inactive: bool,
    ) -> list[RewardItem]:
        with self._lock:
            with self._connect() as connection:
                if include_inactive:
                    rows = connection.execute(
                        """
                        SELECT *
                        FROM reward_items
                        WHERE guild_id = ?
                          AND deleted_at IS NULL
                        ORDER BY is_active DESC, price ASC, id ASC
                        """,
                        (guild_id,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT *
                        FROM reward_items
                        WHERE guild_id = ?
                          AND is_active = 1
                          AND deleted_at IS NULL
                        ORDER BY price ASC, id ASC
                        """,
                        (guild_id,),
                    ).fetchall()
        return [self._row_to_reward(row) for row in rows]

    def _get_reward_sync(self, reward_id: int) -> RewardItem | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM reward_items
                    WHERE id = ?
                    """,
                    (reward_id,),
                ).fetchone()
        return self._row_to_reward(row) if row else None

    def _update_reward_sync(
        self,
        guild_id: int,
        reward_id: int,
        updates: dict[str, Any],
    ) -> RewardItem | None:
        allowed_columns = {
            "name": "name",
            "description": "description",
            "type": "type",
            "price": "price",
            "stock_quantity": "stock_quantity",
            "stock_mode": "stock_mode",
            "max_per_user": "max_per_user",
            "role_id": "role_id",
            "delivery_message": "delivery_message",
            "duration_days": "duration_days",
            "is_active": "is_active",
        }
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            column = allowed_columns.get(key)
            if column is None:
                continue
            assignments.append(f"{column} = ?")
            params.append(value)

        if not assignments:
            reward = self._get_reward_sync(reward_id)
            return reward if reward and reward.guild_id == guild_id else None

        now = serialize_datetime(utc_now())
        assignments.append("updated_at = ?")
        params.append(now)
        params.extend([reward_id, guild_id])

        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    f"""
                    UPDATE reward_items
                    SET {", ".join(assignments)}
                    WHERE id = ?
                      AND guild_id = ?
                      AND deleted_at IS NULL
                    """,
                    params,
                )
                if cursor.rowcount == 0:
                    connection.rollback()
                    return None
                connection.commit()

        return self._get_reward_sync(reward_id)

    def _remove_reward_sync(
        self,
        guild_id: int,
        reward_id: int,
    ) -> RewardItem | None:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE reward_items
                    SET is_active = 0,
                        deleted_at = ?,
                        updated_at = ?
                    WHERE id = ?
                      AND guild_id = ?
                      AND deleted_at IS NULL
                    """,
                    (now, now, reward_id, guild_id),
                )
                if cursor.rowcount == 0:
                    connection.rollback()
                    return None
                connection.commit()

        return self._get_reward_sync(reward_id)

    def _purchase_reward_sync(
        self,
        guild_id: int,
        user_id: int,
        reward_id: int,
        metadata: dict[str, Any],
    ) -> ShopPurchaseResult:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                reward_row = connection.execute(
                    """
                    SELECT *
                    FROM reward_items
                    WHERE id = ? AND guild_id = ?
                    """,
                    (reward_id, guild_id),
                ).fetchone()
                if reward_row is None:
                    connection.rollback()
                    return ShopPurchaseResult(
                        status=ShopPurchaseStatus.REWARD_NOT_FOUND
                    )

                reward = self._row_to_reward(reward_row)
                if not reward.is_active or reward.deleted_at is not None:
                    connection.rollback()
                    return ShopPurchaseResult(
                        status=ShopPurchaseStatus.REWARD_INACTIVE,
                        reward=reward,
                    )

                if reward.stock_mode is StockMode.LIMITED and (
                    reward.stock_quantity is None or reward.stock_quantity <= 0
                ):
                    connection.rollback()
                    return ShopPurchaseResult(
                        status=ShopPurchaseStatus.OUT_OF_STOCK,
                        reward=reward,
                    )

                purchase_count = 0
                if reward.max_per_user is not None:
                    count_row = connection.execute(
                        """
                        SELECT COUNT(*) AS purchase_count
                        FROM reward_purchases
                        WHERE guild_id = ?
                          AND reward_id = ?
                          AND user_id = ?
                          AND status != ?
                        """,
                        (
                            guild_id,
                            reward_id,
                            user_id,
                            PurchaseStatus.CANCELLED.value,
                        ),
                    ).fetchone()
                    purchase_count = int(count_row["purchase_count"] or 0)
                    if purchase_count >= reward.max_per_user:
                        connection.rollback()
                        return ShopPurchaseResult(
                            status=ShopPurchaseStatus.LIMIT_REACHED,
                            reward=reward,
                        )

                wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                balance_before = int(wallet_row["balance"])
                if balance_before < reward.price:
                    connection.rollback()
                    return ShopPurchaseResult(
                        status=ShopPurchaseStatus.INSUFFICIENT_BALANCE,
                        reward=reward,
                        balance_before=balance_before,
                        balance_after=balance_before,
                        missing_points=reward.price - balance_before,
                    )

                now = serialize_datetime(utc_now())
                balance_after = balance_before - reward.price
                connection.execute(
                    """
                    UPDATE user_wallets
                    SET balance = ?,
                        total_spent = total_spent + ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (balance_after, reward.price, now, guild_id, user_id),
                )
                transaction = self._insert_transaction(
                    connection,
                    guild_id=guild_id,
                    user_id=user_id,
                    actor_id=user_id,
                    transaction_type=EconomyTransactionType.SHOP_PURCHASE,
                    amount=-reward.price,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    reason=f"shop_purchase:{reward.id}",
                    metadata={"reward_id": reward.id, "reward_name": reward.name},
                    created_at=now,
                )
                if reward.stock_mode is StockMode.LIMITED:
                    connection.execute(
                        """
                        UPDATE reward_items
                        SET stock_quantity = stock_quantity - 1,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (now, reward.id),
                    )

                delivery_status = (
                    DeliveryStatus.PENDING
                    if reward.type in {RewardType.MANUAL_REWARD, RewardType.ROLE}
                    else DeliveryStatus.DELIVERED
                )
                purchase_cursor = connection.execute(
                    """
                    INSERT INTO reward_purchases (
                        guild_id,
                        user_id,
                        reward_id,
                        transaction_id,
                        price_paid,
                        status,
                        delivery_status,
                        metadata_json,
                        created_at,
                        delivered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        user_id,
                        reward.id,
                        transaction.id,
                        reward.price,
                        PurchaseStatus.COMPLETED.value,
                        delivery_status.value,
                        json.dumps(metadata, ensure_ascii=True),
                        now,
                        now if delivery_status is DeliveryStatus.DELIVERED else None,
                    ),
                )
                connection.commit()

        purchase = self._get_purchase_sync(int(purchase_cursor.lastrowid))
        updated_reward = self._get_reward_sync(reward.id) or reward
        return ShopPurchaseResult(
            status=ShopPurchaseStatus.SUCCESS,
            reward=updated_reward,
            purchase=purchase,
            balance_before=balance_before,
            balance_after=balance_after,
        )

    def _list_purchases_sync(
        self,
        guild_id: int,
        user_id: int,
        limit: int,
    ) -> list[RewardPurchase]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM reward_purchases
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (guild_id, user_id, max(1, min(limit, 50))),
                ).fetchall()
        return [self._row_to_purchase(row) for row in rows]

    def _get_purchase_sync(self, purchase_id: int) -> RewardPurchase | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM reward_purchases
                    WHERE id = ?
                    """,
                    (purchase_id,),
                ).fetchone()
        return self._row_to_purchase(row) if row else None

    def _upsert_level_config_sync(
        self,
        guild_id: int,
        level: int,
        role_id: int,
        price: int,
        is_active: bool,
        created_by: int,
        saves_reward: int,
    ) -> LevelConfig:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO shop_level_configs (
                        guild_id,
                        level,
                        role_id,
                        price,
                        saves_reward,
                        is_active,
                        created_by,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, level) DO UPDATE SET
                        role_id = excluded.role_id,
                        price = excluded.price,
                        saves_reward = excluded.saves_reward,
                        is_active = excluded.is_active,
                        updated_at = excluded.updated_at
                    """,
                    (
                        guild_id,
                        level,
                        role_id,
                        price,
                        saves_reward,
                        int(is_active),
                        created_by,
                        now,
                        now,
                    ),
                )
                connection.commit()

        config = self._get_level_config_sync(guild_id, level)
        if config is None:
            raise RuntimeError("Nao foi possivel recuperar o nivel configurado.")
        return config

    def _list_level_configs_sync(
        self,
        guild_id: int,
        include_inactive: bool,
    ) -> list[LevelConfig]:
        with self._lock:
            with self._connect() as connection:
                if include_inactive:
                    rows = connection.execute(
                        """
                        SELECT *
                        FROM shop_level_configs
                        WHERE guild_id = ?
                        ORDER BY level ASC
                        """,
                        (guild_id,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT *
                        FROM shop_level_configs
                        WHERE guild_id = ?
                          AND is_active = 1
                        ORDER BY level ASC
                        """,
                        (guild_id,),
                    ).fetchall()
        return [self._row_to_level_config(row) for row in rows]

    def _get_level_config_sync(
        self,
        guild_id: int,
        level: int,
    ) -> LevelConfig | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM shop_level_configs
                    WHERE guild_id = ? AND level = ?
                    """,
                    (guild_id, level),
                ).fetchone()
        return self._row_to_level_config(row) if row else None

    def _list_user_level_upgrades_sync(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[LevelUpgradePurchase]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM user_level_upgrades
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY level ASC, id ASC
                    """,
                    (guild_id, user_id),
                ).fetchall()
        return [self._row_to_level_purchase(row) for row in rows]

    def _purchase_level_upgrade_sync(
        self,
        guild_id: int,
        user_id: int,
        level: int,
    ) -> LevelUpgradeResult:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                level_row = connection.execute(
                    """
                    SELECT *
                    FROM shop_level_configs
                    WHERE guild_id = ? AND level = ?
                    """,
                    (guild_id, level),
                ).fetchone()
                if level_row is None:
                    connection.rollback()
                    return LevelUpgradeResult(
                        status=LevelUpgradeStatus.LEVEL_NOT_FOUND,
                    )

                level_config = self._row_to_level_config(level_row)
                if not level_config.is_active:
                    connection.rollback()
                    return LevelUpgradeResult(
                        status=LevelUpgradeStatus.LEVEL_INACTIVE,
                        level_config=level_config,
                    )

                existing = connection.execute(
                    """
                    SELECT 1
                    FROM user_level_upgrades
                    WHERE guild_id = ? AND user_id = ? AND level = ?
                    """,
                    (guild_id, user_id, level),
                ).fetchone()
                if existing is not None:
                    connection.rollback()
                    return LevelUpgradeResult(
                        status=LevelUpgradeStatus.ALREADY_OWNED,
                        level_config=level_config,
                    )

                wallet_row = self._ensure_wallet(connection, guild_id, user_id)
                balance_before = int(wallet_row["balance"])
                if balance_before < level_config.price:
                    connection.rollback()
                    return LevelUpgradeResult(
                        status=LevelUpgradeStatus.INSUFFICIENT_BALANCE,
                        level_config=level_config,
                        balance_before=balance_before,
                        balance_after=balance_before,
                        missing_points=level_config.price - balance_before,
                    )

                now = serialize_datetime(utc_now())
                balance_after = balance_before - level_config.price
                connection.execute(
                    """
                    UPDATE user_wallets
                    SET balance = ?,
                        total_spent = total_spent + ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (
                        balance_after,
                        level_config.price,
                        now,
                        guild_id,
                        user_id,
                    ),
                )
                transaction = self._insert_transaction(
                    connection,
                    guild_id=guild_id,
                    user_id=user_id,
                    actor_id=user_id,
                    transaction_type=EconomyTransactionType.LEVEL_UPGRADE,
                    amount=-level_config.price,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    reason=f"level_upgrade:{level_config.level}",
                    metadata={
                        "level": level_config.level,
                        "role_id": level_config.role_id,
                        "saves_reward": level_config.saves_reward,
                    },
                    created_at=now,
                )
                if level_config.saves_reward > 0:
                    protection_row = self._ensure_credit_protection_state(
                        connection,
                        guild_id,
                        user_id,
                    )
                    connection.execute(
                        """
                        UPDATE user_credit_protection
                        SET saves = ?,
                            updated_at = ?
                        WHERE guild_id = ? AND user_id = ?
                        """,
                        (
                            int(protection_row["saves"]) + level_config.saves_reward,
                            now,
                            guild_id,
                            user_id,
                        ),
                    )
                try:
                    purchase_cursor = connection.execute(
                        """
                        INSERT INTO user_level_upgrades (
                            guild_id,
                            user_id,
                            level,
                            role_id,
                            transaction_id,
                            price_paid,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            guild_id,
                            user_id,
                            level_config.level,
                            level_config.role_id,
                            transaction.id,
                            level_config.price,
                            now,
                        ),
                    )
                except sqlite3.IntegrityError:
                    connection.rollback()
                    return LevelUpgradeResult(
                        status=LevelUpgradeStatus.ALREADY_OWNED,
                        level_config=level_config,
                    )
                connection.commit()

        purchase = self._get_level_purchase_sync(int(purchase_cursor.lastrowid))
        if purchase is None:
            raise RuntimeError("Nao foi possivel recuperar a compra de nivel.")
        return LevelUpgradeResult(
            status=LevelUpgradeStatus.SUCCESS,
            level_config=level_config,
            purchase=purchase,
            balance_before=balance_before,
            balance_after=balance_after,
        )

    def _get_level_purchase_sync(
        self,
        purchase_id: int,
    ) -> LevelUpgradePurchase | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM user_level_upgrades
                    WHERE id = ?
                    """,
                    (purchase_id,),
                ).fetchone()
        return self._row_to_level_purchase(row) if row else None

    @staticmethod
    def _get_settings_row(
        connection: sqlite3.Connection,
        guild_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT *
            FROM guild_settings
            WHERE guild_id = ?
            """,
            (guild_id,),
        ).fetchone()

    def _ensure_settings(
        self,
        connection: sqlite3.Connection,
        guild_id: int,
    ) -> sqlite3.Row:
        row = self._get_settings_row(connection, guild_id)
        if row is not None:
            return row

        now = serialize_datetime(utc_now())
        connection.execute(
            """
            INSERT INTO guild_settings (guild_id, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (guild_id, now, now),
        )
        row = self._get_settings_row(connection, guild_id)
        if row is None:
            raise RuntimeError("Nao foi possivel criar configuracao da guild.")
        return row

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
        if any(existing["name"] == column for existing in columns):
            return
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _get_wallet_row(
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT *
            FROM user_wallets
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ).fetchone()

    def _ensure_wallet(
        self,
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
    ) -> sqlite3.Row:
        row = self._get_wallet_row(connection, guild_id, user_id)
        if row is not None:
            return row

        now = serialize_datetime(utc_now())
        connection.execute(
            """
            INSERT INTO user_wallets (
                guild_id,
                user_id,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, now, now),
        )
        row = self._get_wallet_row(connection, guild_id, user_id)
        if row is None:
            raise RuntimeError("Nao foi possivel criar carteira.")
        return row

    @staticmethod
    def _get_savings_account_row(
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT *
            FROM user_savings_accounts
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ).fetchone()

    def _ensure_savings_account(
        self,
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
    ) -> sqlite3.Row:
        row = self._get_savings_account_row(connection, guild_id, user_id)
        if row is not None:
            return row

        now = serialize_datetime(utc_now())
        connection.execute(
            """
            INSERT INTO user_savings_accounts (
                guild_id,
                user_id,
                last_interest_at,
                updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO NOTHING
            """,
            (guild_id, user_id, now, now),
        )
        row = self._get_savings_account_row(connection, guild_id, user_id)
        if row is None:
            raise RuntimeError("Não foi possível criar poupança.")
        return row

    def _apply_savings_interest(
        self,
        connection: sqlite3.Connection,
        account_row: sqlite3.Row,
        daily_interest_bps: int,
    ) -> int:
        balance = int(account_row["balance"])
        bps = max(0, int(daily_interest_bps))
        if balance <= 0:
            return 0

        now_dt = utc_now()
        last_interest_at = parse_datetime(str(account_row["last_interest_at"]))
        elapsed_days = int((now_dt - last_interest_at).total_seconds() // 86400)
        if elapsed_days <= 0:
            return 0

        next_interest_at = last_interest_at + timedelta(days=elapsed_days)
        now = serialize_datetime(now_dt)
        if bps <= 0:
            connection.execute(
                """
                UPDATE user_savings_accounts
                SET last_interest_at = ?,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (
                    serialize_datetime(next_interest_at),
                    now,
                    int(account_row["guild_id"]),
                    int(account_row["user_id"]),
                ),
            )
            return 0

        interest_total = 0
        new_balance = balance
        for _ in range(elapsed_days):
            daily_interest = (new_balance * bps) // 10000
            if daily_interest > 0:
                new_balance += daily_interest
                interest_total += daily_interest

        connection.execute(
            """
            UPDATE user_savings_accounts
            SET balance = ?,
                total_interest_earned = total_interest_earned + ?,
                last_interest_at = ?,
                updated_at = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (
                new_balance,
                interest_total,
                serialize_datetime(next_interest_at),
                now,
                int(account_row["guild_id"]),
                int(account_row["user_id"]),
            ),
        )
        return interest_total

    def _build_savings_overview(
        self,
        wallet_row: sqlite3.Row,
        account_row: sqlite3.Row,
        daily_interest_bps: int,
        interest_applied: int,
    ) -> SavingsOverview:
        wallet = self._row_to_wallet(wallet_row)
        return SavingsOverview(
            wallet=wallet,
            account=self._row_to_savings_account(account_row),
            daily_interest_bps=max(0, int(daily_interest_bps)),
            max_deposit=self._calculate_max_savings_deposit(wallet.balance),
            interest_applied=interest_applied,
        )

    @classmethod
    def _calculate_max_savings_deposit(cls, wallet_balance: int) -> int:
        return max(0, (int(wallet_balance) * cls.SAVINGS_MAX_DEPOSIT_PERCENT) // 100)

    @staticmethod
    def _get_credit_protection_row(
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT *
            FROM user_credit_protection
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ).fetchone()

    def _ensure_credit_protection_state(
        self,
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
    ) -> sqlite3.Row:
        row = self._get_credit_protection_row(connection, guild_id, user_id)
        if row is not None:
            return row

        now = serialize_datetime(utc_now())
        connection.execute(
            """
            INSERT INTO user_credit_protection (
                guild_id,
                user_id,
                saves,
                lose_streak,
                updated_at
            ) VALUES (?, ?, 0, 0, ?)
            """,
            (guild_id, user_id, now),
        )
        row = self._get_credit_protection_row(connection, guild_id, user_id)
        if row is None:
            raise RuntimeError("Nao foi possivel criar protecao de credito.")
        return row

    @staticmethod
    def _get_cursor_row(
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT *
            FROM activity_claim_cursors
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ).fetchone()

    def _ensure_cursor(
        self,
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
    ) -> sqlite3.Row:
        row = self._get_cursor_row(connection, guild_id, user_id)
        if row is not None:
            return row

        connection.execute(
            """
            INSERT INTO activity_claim_cursors (guild_id, user_id)
            VALUES (?, ?)
            """,
            (guild_id, user_id),
        )
        row = self._get_cursor_row(connection, guild_id, user_id)
        if row is None:
            raise RuntimeError("Nao foi possivel criar cursor.")
        return row

    @staticmethod
    def _get_reward_claim_row(
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
        reward_key: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT last_claim_date, claim_count
            FROM economy_reward_claims
            WHERE guild_id = ?
              AND user_id = ?
              AND reward_key = ?
            """,
            (guild_id, user_id, reward_key),
        ).fetchone()

    def _insert_reward_claim(
        self,
        connection: sqlite3.Connection,
        *,
        guild_id: int,
        user_id: int,
        reward_key: str,
        claim_date: str | None,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO economy_reward_claims (
                guild_id,
                user_id,
                reward_key,
                last_claimed_at,
                last_claim_date,
                claim_count
            ) VALUES (?, ?, ?, ?, ?, 1)
            """,
            (guild_id, user_id, reward_key, now, claim_date),
        )

    def _update_reward_claim(
        self,
        connection: sqlite3.Connection,
        *,
        guild_id: int,
        user_id: int,
        reward_key: str,
        claim_date: str | None,
        claim_count: int,
        now: str,
    ) -> None:
        connection.execute(
            """
            UPDATE economy_reward_claims
            SET last_claimed_at = ?,
                last_claim_date = ?,
                claim_count = ?
            WHERE guild_id = ?
              AND user_id = ?
              AND reward_key = ?
            """,
            (
                now,
                claim_date,
                claim_count,
                guild_id,
                user_id,
                reward_key,
            ),
        )

    def _upsert_reward_claim(
        self,
        connection: sqlite3.Connection,
        *,
        guild_id: int,
        user_id: int,
        reward_key: str,
        claim_date: str | None,
        now: str,
    ) -> None:
        row = self._get_reward_claim_row(connection, guild_id, user_id, reward_key)
        if row is None:
            self._insert_reward_claim(
                connection,
                guild_id=guild_id,
                user_id=user_id,
                reward_key=reward_key,
                claim_date=claim_date,
                now=now,
            )
            return
        self._update_reward_claim(
            connection,
            guild_id=guild_id,
            user_id=user_id,
            reward_key=reward_key,
            claim_date=claim_date,
            claim_count=max(1, int(row["claim_count"])),
            now=now,
        )

    @staticmethod
    def _has_achievement_reward_transaction(
        connection: sqlite3.Connection,
        guild_id: int,
        user_id: int,
        achievement_key: str,
    ) -> bool:
        rows = connection.execute(
            """
            SELECT metadata_json
            FROM economy_transactions
            WHERE guild_id = ?
              AND user_id = ?
              AND reason = 'achievement_reward'
            """,
            (guild_id, user_id),
        ).fetchall()
        for row in rows:
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except json.JSONDecodeError:
                continue
            if metadata.get("achievement_key") == achievement_key:
                return True
        return False

    def _insert_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        guild_id: int,
        user_id: int,
        actor_id: int | None,
        transaction_type: EconomyTransactionType,
        amount: int,
        balance_before: int,
        balance_after: int,
        reason: str | None,
        metadata: dict[str, Any],
        created_at: str,
    ) -> EconomyTransaction:
        cursor = connection.execute(
            """
            INSERT INTO economy_transactions (
                guild_id,
                user_id,
                actor_id,
                type,
                amount,
                balance_before,
                balance_after,
                reason,
                metadata_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                user_id,
                actor_id,
                transaction_type.value,
                amount,
                balance_before,
                balance_after,
                reason,
                json.dumps(metadata, ensure_ascii=True),
                created_at,
            ),
        )
        return EconomyTransaction(
            id=int(cursor.lastrowid),
            guild_id=guild_id,
            user_id=user_id,
            actor_id=actor_id,
            type=transaction_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reason=reason,
            metadata=metadata,
            created_at=parse_datetime(created_at),
        )

    @staticmethod
    def _row_to_settings(row: sqlite3.Row) -> GuildEconomySettings:
        return GuildEconomySettings(
            guild_id=int(row["guild_id"]),
            currency_name=str(row["currency_name"]),
            voice_points_per_minute=int(row["voice_points_per_minute"]),
            message_points=int(row["message_points"]),
            activity_provider=str(row["activity_provider"]),
            economy_channel_id=(
                int(row["economy_channel_id"])
                if row["economy_channel_id"] is not None
                else None
            ),
            shop_channel_id=(
                int(row["shop_channel_id"])
                if row["shop_channel_id"] is not None
                else None
            ),
            staff_log_channel_id=(
                int(row["staff_log_channel_id"])
                if row["staff_log_channel_id"] is not None
                else None
            ),
            min_voice_seconds_to_claim=int(row["min_voice_seconds_to_claim"]),
            min_messages_to_claim=int(row["min_messages_to_claim"]),
            ignore_afk_channel=bool(row["ignore_afk_channel"]),
            ignore_bots=bool(row["ignore_bots"]),
            count_voice_when_alone=bool(row["count_voice_when_alone"]),
            max_admin_grant_per_use=int(row["max_admin_grant_per_use"]),
            casino_max_bet=int(row["casino_max_bet"]),
            casino_daily_profit_limit=int(row["casino_daily_profit_limit"]),
            casino_min_bet_coin_flip=int(row["casino_min_bet_coin_flip"]),
            casino_min_bet_dice=int(row["casino_min_bet_dice"]),
            casino_min_bet_slot=int(row["casino_min_bet_slot"]),
            casino_min_bet_roulette=int(row["casino_min_bet_roulette"]),
            casino_min_bet_mascot_race=int(row["casino_min_bet_mascot_race"]),
            casino_min_bet_duel=int(row["casino_min_bet_duel"]),
            casino_min_bet_blackjack=int(row["casino_min_bet_blackjack"]),
            casino_min_bet_scratch_card=int(row["casino_min_bet_scratch_card"]),
            casino_min_bet_collective_race=int(
                row["casino_min_bet_collective_race"]
            ),
            casino_min_bet_match_bet=int(row["casino_min_bet_match_bet"]),
            casino_min_bet_truco=int(row["casino_min_bet_truco"]),
            casino_limiters_enabled=bool(row["casino_limiters_enabled"]),
            savings_daily_interest_bps=int(row["savings_daily_interest_bps"]),
            economy_manager_role_id=(
                int(row["economy_manager_role_id"])
                if row["economy_manager_role_id"] is not None
                else None
            ),
            created_at=parse_datetime(str(row["created_at"])),
            updated_at=parse_datetime(str(row["updated_at"])),
        )

    @staticmethod
    def _row_to_wallet(row: sqlite3.Row) -> UserWallet:
        return UserWallet(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            balance=int(row["balance"]),
            total_earned=int(row["total_earned"]),
            total_spent=int(row["total_spent"]),
            created_at=parse_datetime(str(row["created_at"])),
            updated_at=parse_datetime(str(row["updated_at"])),
        )

    @staticmethod
    def _row_to_credit_protection_state(row: sqlite3.Row) -> CreditProtectionState:
        return CreditProtectionState(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            saves=int(row["saves"]),
            lose_streak=int(row["lose_streak"]),
            updated_at=parse_datetime(str(row["updated_at"])),
        )

    @staticmethod
    def _row_to_savings_account(row: sqlite3.Row) -> SavingsAccount:
        return SavingsAccount(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            balance=int(row["balance"]),
            total_interest_earned=int(row["total_interest_earned"]),
            last_interest_at=parse_datetime(str(row["last_interest_at"])),
            locked_until=(
                parse_datetime(str(row["locked_until"]))
                if row["locked_until"] is not None
                else None
            ),
            updated_at=parse_datetime(str(row["updated_at"])),
        )

    @staticmethod
    def _row_to_transaction(row: sqlite3.Row) -> EconomyTransaction:
        return EconomyTransaction(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            actor_id=int(row["actor_id"]) if row["actor_id"] is not None else None,
            type=EconomyTransactionType(str(row["type"])),
            amount=int(row["amount"]),
            balance_before=int(row["balance_before"]),
            balance_after=int(row["balance_after"]),
            reason=str(row["reason"]) if row["reason"] is not None else None,
            metadata=json.loads(str(row["metadata_json"] or "{}")),
            created_at=parse_datetime(str(row["created_at"])),
        )

    @staticmethod
    def _row_to_cursor(row: sqlite3.Row) -> ActivityClaimCursor:
        return ActivityClaimCursor(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            claimed_voice_seconds=int(row["claimed_voice_seconds"]),
            claimed_messages=int(row["claimed_messages"]),
            last_claimed_at=(
                parse_datetime(str(row["last_claimed_at"]))
                if row["last_claimed_at"] is not None
                else None
            ),
            last_source=(
                str(row["last_source"]) if row["last_source"] is not None else None
            ),
        )

    @staticmethod
    def _row_to_voice_session(row: sqlite3.Row) -> NativeVoiceSession:
        return NativeVoiceSession(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            channel_id=int(row["channel_id"]),
            started_at=parse_datetime(str(row["started_at"])),
            ended_at=(
                parse_datetime(str(row["ended_at"]))
                if row["ended_at"] is not None
                else None
            ),
            duration_seconds=(
                int(row["duration_seconds"])
                if row["duration_seconds"] is not None
                else None
            ),
            is_valid=bool(row["is_valid"]),
            invalid_reason=(
                str(row["invalid_reason"])
                if row["invalid_reason"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_reward(row: sqlite3.Row) -> RewardItem:
        return RewardItem(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            type=RewardType(str(row["type"])),
            price=int(row["price"]),
            stock_quantity=(
                int(row["stock_quantity"])
                if row["stock_quantity"] is not None
                else None
            ),
            stock_mode=StockMode(str(row["stock_mode"])),
            max_per_user=(
                int(row["max_per_user"]) if row["max_per_user"] is not None else None
            ),
            role_id=int(row["role_id"]) if row["role_id"] is not None else None,
            delivery_message=(
                str(row["delivery_message"])
                if row["delivery_message"] is not None
                else None
            ),
            duration_days=(
                int(row["duration_days"])
                if row["duration_days"] is not None
                else None
            ),
            is_active=bool(row["is_active"]),
            created_by=int(row["created_by"]),
            created_at=parse_datetime(str(row["created_at"])),
            updated_at=parse_datetime(str(row["updated_at"])),
            deleted_at=(
                parse_datetime(str(row["deleted_at"]))
                if row["deleted_at"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_purchase(row: sqlite3.Row) -> RewardPurchase:
        return RewardPurchase(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            reward_id=int(row["reward_id"]),
            transaction_id=(
                int(row["transaction_id"])
                if row["transaction_id"] is not None
                else None
            ),
            price_paid=int(row["price_paid"]),
            status=PurchaseStatus(str(row["status"])),
            delivery_status=DeliveryStatus(str(row["delivery_status"])),
            metadata=json.loads(str(row["metadata_json"] or "{}")),
            created_at=parse_datetime(str(row["created_at"])),
            delivered_at=(
                parse_datetime(str(row["delivered_at"]))
                if row["delivered_at"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_level_config(row: sqlite3.Row) -> LevelConfig:
        return LevelConfig(
            guild_id=int(row["guild_id"]),
            level=int(row["level"]),
            role_id=int(row["role_id"]),
            price=int(row["price"]),
            is_active=bool(row["is_active"]),
            created_by=int(row["created_by"]),
            created_at=parse_datetime(str(row["created_at"])),
            updated_at=parse_datetime(str(row["updated_at"])),
            saves_reward=int(row["saves_reward"]),
        )

    @staticmethod
    def _row_to_level_purchase(row: sqlite3.Row) -> LevelUpgradePurchase:
        return LevelUpgradePurchase(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            level=int(row["level"]),
            role_id=int(row["role_id"]),
            transaction_id=int(row["transaction_id"]),
            price_paid=int(row["price_paid"]),
            created_at=parse_datetime(str(row["created_at"])),
        )
