from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.models.activity import ActivityStats, NativeVoiceSession
from app.models.audit import AdminAuditLog
from app.models.economy import (
    ActivityClaimCursor,
    ActivityConversionResult,
    BalanceMutationResult,
    EconomyTransaction,
    EconomyTransactionType,
    UserWallet,
)
from app.models.giveaway import parse_datetime, serialize_datetime, utc_now
from app.models.guild_settings import GuildEconomySettings
from app.models.shop import (
    DeliveryStatus,
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

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize_schema()

    async def get_guild_settings(self, guild_id: int) -> GuildEconomySettings:
        return await asyncio.to_thread(self._get_or_create_settings_sync, guild_id)

    async def get_wallet(self, guild_id: int, user_id: int) -> UserWallet:
        return await asyncio.to_thread(
            self._get_or_create_wallet_sync,
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
                        economy_manager_role_id INTEGER,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """)
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
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        deleted_at TEXT
                    )
                    """)
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

    def _get_or_create_wallet_sync(self, guild_id: int, user_id: int) -> UserWallet:
        with self._lock:
            with self._connect() as connection:
                row = self._ensure_wallet(connection, guild_id, user_id)
        return self._row_to_wallet(row)

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
            self._close_voice_sessions_sync(guild_id, user_id, "superseded")
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
                        is_active,
                        created_by,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
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
