from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from app.models.giveaway import (
    GiveawayClaim,
    GiveawayCode,
    GiveawayCodeSeed,
    GiveawayDrawResult,
    GiveawayDrawStatus,
    GiveawayEvent,
    GiveawayEventCreate,
    GiveawayEventStats,
    GiveawayFinalizationResult,
    GiveawayTicketBalance,
    parse_datetime,
    serialize_datetime,
    utc_now,
)


class GiveawayRepositoryProtocol(Protocol):
    """Contrato esperado pela camada de service."""

    async def create_event(
        self,
        event: GiveawayEventCreate,
        code_seeds: Sequence[GiveawayCodeSeed],
    ) -> GiveawayEvent: ...

    async def get_event(self, event_id: int) -> GiveawayEvent | None: ...

    async def get_event_by_message_id(
        self, message_id: int
    ) -> GiveawayEvent | None: ...

    async def list_active_published_events(self) -> list[GiveawayEvent]: ...

    async def update_event_publication(
        self,
        event_id: int,
        *,
        channel_id: int,
        message_id: int,
        embed_color: int | None = None,
        expires_at: str | None = None,
    ) -> GiveawayEvent: ...

    async def set_event_active(
        self,
        event_id: int,
        *,
        is_active: bool,
    ) -> GiveawayEvent | None: ...

    async def get_event_stats(self, event_id: int) -> GiveawayEventStats | None: ...

    async def get_user_claim(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayClaim | None: ...

    async def get_user_ticket_balance(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayTicketBalance: ...

    async def add_user_tickets(
        self,
        event_id: int,
        user_id: int,
        amount: int,
    ) -> GiveawayTicketBalance: ...

    async def remove_user_tickets(
        self,
        event_id: int,
        user_id: int,
        amount: int,
    ) -> GiveawayTicketBalance: ...

    async def claim_next_available_code(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayDrawResult: ...

    async def list_remaining_codes(self, event_id: int) -> list[GiveawayCode]: ...

    async def get_events_expiring_at_or_before(
        self,
        moment: str,
    ) -> list[GiveawayEvent]: ...

    async def finalize_event(self, event_id: int) -> GiveawayFinalizationResult: ...


class SQLiteGiveawayRepository:
    """Persistencia SQLite para eventos, codigos e resgates."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize_schema()

    async def create_event(
        self,
        event: GiveawayEventCreate,
        code_seeds: Sequence[GiveawayCodeSeed],
    ) -> GiveawayEvent:
        return await asyncio.to_thread(
            self._create_event_sync,
            event,
            tuple(code_seeds),
        )

    async def get_event(self, event_id: int) -> GiveawayEvent | None:
        return await asyncio.to_thread(self._get_event_sync, event_id)

    async def get_event_by_message_id(self, message_id: int) -> GiveawayEvent | None:
        return await asyncio.to_thread(self._get_event_by_message_id_sync, message_id)

    async def list_active_published_events(self) -> list[GiveawayEvent]:
        return await asyncio.to_thread(self._list_active_published_events_sync)

    async def update_event_publication(
        self,
        event_id: int,
        *,
        channel_id: int,
        message_id: int,
        embed_color: int | None = None,
        expires_at: str | None = None,
    ) -> GiveawayEvent:
        return await asyncio.to_thread(
            self._update_event_publication_sync,
            event_id,
            channel_id,
            message_id,
            embed_color,
            expires_at,
        )

    async def set_event_active(
        self,
        event_id: int,
        *,
        is_active: bool,
    ) -> GiveawayEvent | None:
        return await asyncio.to_thread(
            self._set_event_active_sync,
            event_id,
            is_active,
        )

    async def get_event_stats(self, event_id: int) -> GiveawayEventStats | None:
        return await asyncio.to_thread(self._get_event_stats_sync, event_id)

    async def get_user_claim(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayClaim | None:
        return await asyncio.to_thread(self._get_user_claim_sync, event_id, user_id)

    async def get_user_ticket_balance(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayTicketBalance:
        return await asyncio.to_thread(
            self._get_user_ticket_balance_sync,
            event_id,
            user_id,
        )

    async def add_user_tickets(
        self,
        event_id: int,
        user_id: int,
        amount: int,
    ) -> GiveawayTicketBalance:
        return await asyncio.to_thread(
            self._add_user_tickets_sync,
            event_id,
            user_id,
            amount,
        )

    async def remove_user_tickets(
        self,
        event_id: int,
        user_id: int,
        amount: int,
    ) -> GiveawayTicketBalance:
        return await asyncio.to_thread(
            self._remove_user_tickets_sync,
            event_id,
            user_id,
            amount,
        )

    async def claim_next_available_code(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayDrawResult:
        return await asyncio.to_thread(
            self._claim_next_available_code_sync,
            event_id,
            user_id,
        )

    async def list_remaining_codes(self, event_id: int) -> list[GiveawayCode]:
        return await asyncio.to_thread(self._list_remaining_codes_sync, event_id)

    async def get_events_expiring_at_or_before(
        self,
        moment: str,
    ) -> list[GiveawayEvent]:
        return await asyncio.to_thread(
            self._get_events_expiring_at_or_before_sync, moment
        )

    async def finalize_event(self, event_id: int) -> GiveawayFinalizationResult:
        return await asyncio.to_thread(self._finalize_event_sync, event_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_schema(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS giveaway_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        max_redemptions INTEGER,
                        total_codes INTEGER NOT NULL,
                        notify_user_id INTEGER,
                        embed_color INTEGER,
                        expires_at TEXT
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS giveaway_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id INTEGER NOT NULL,
                        code TEXT NOT NULL,
                        reward_name TEXT,
                        reward_amount INTEGER,
                        is_claimed INTEGER NOT NULL DEFAULT 0,
                        claimed_by INTEGER,
                        claimed_at TEXT,
                        FOREIGN KEY(event_id) REFERENCES giveaway_events(id)
                            ON DELETE CASCADE,
                        UNIQUE(event_id, code)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS giveaway_claims (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        code_id INTEGER NOT NULL UNIQUE,
                        claimed_at TEXT NOT NULL,
                        reward_amount INTEGER,
                        reward_name TEXT,
                        FOREIGN KEY(event_id) REFERENCES giveaway_events(id)
                            ON DELETE CASCADE,
                        FOREIGN KEY(code_id) REFERENCES giveaway_codes(id)
                            ON DELETE CASCADE,
                        UNIQUE(event_id, user_id)
                    )
                    """)
                self._ensure_claims_allow_multiple_per_user(connection)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS giveaway_user_tickets (
                        event_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        extra_tickets INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(event_id, user_id),
                        FOREIGN KEY(event_id) REFERENCES giveaway_events(id)
                            ON DELETE CASCADE
                    )
                    """)
                self._ensure_column(
                    connection, "giveaway_events", "notify_user_id", "INTEGER"
                )
                self._ensure_column(
                    connection, "giveaway_events", "embed_color", "INTEGER"
                )
                self._ensure_column(connection, "giveaway_events", "expires_at", "TEXT")
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_giveaway_codes_event_claimed
                    ON giveaway_codes(event_id, is_claimed)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_giveaway_claims_event_user
                    ON giveaway_claims(event_id, user_id)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_giveaway_tickets_event_user
                    ON giveaway_user_tickets(event_id, user_id)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_giveaway_events_expires_at
                    ON giveaway_events(is_active, expires_at)
                    """)

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
    def _ensure_claims_allow_multiple_per_user(
        connection: sqlite3.Connection,
    ) -> None:
        indexes = connection.execute("PRAGMA index_list(giveaway_claims)").fetchall()
        has_user_unique = False
        for index in indexes:
            if not bool(index["unique"]):
                continue

            columns = connection.execute(
                f"PRAGMA index_info({index['name']})"
            ).fetchall()
            column_names = [str(column["name"]) for column in columns]
            if column_names == ["event_id", "user_id"]:
                has_user_unique = True
                break

        if not has_user_unique:
            return

        connection.execute("ALTER TABLE giveaway_claims RENAME TO giveaway_claims_old")
        connection.execute("""
            CREATE TABLE giveaway_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                code_id INTEGER NOT NULL UNIQUE,
                claimed_at TEXT NOT NULL,
                reward_amount INTEGER,
                reward_name TEXT,
                FOREIGN KEY(event_id) REFERENCES giveaway_events(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(code_id) REFERENCES giveaway_codes(id)
                    ON DELETE CASCADE
            )
            """)
        connection.execute("""
            INSERT INTO giveaway_claims (
                id,
                event_id,
                user_id,
                code_id,
                claimed_at,
                reward_amount,
                reward_name
            )
            SELECT
                id,
                event_id,
                user_id,
                code_id,
                claimed_at,
                reward_amount,
                reward_name
            FROM giveaway_claims_old
            """)
        connection.execute("DROP TABLE giveaway_claims_old")

    def _create_event_sync(
        self,
        event: GiveawayEventCreate,
        code_seeds: Sequence[GiveawayCodeSeed],
    ) -> GiveawayEvent:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT INTO giveaway_events (
                        title,
                        description,
                        channel_id,
                        message_id,
                        created_by,
                        created_at,
                        is_active,
                        max_redemptions,
                        total_codes,
                        notify_user_id,
                        embed_color,
                        expires_at
                    ) VALUES (?, ?, NULL, NULL, ?, ?, 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.title,
                        event.description,
                        event.created_by,
                        serialize_datetime(event.created_at),
                        event.max_redemptions,
                        event.total_codes,
                        event.notify_user_id,
                        event.embed_color,
                        (
                            serialize_datetime(event.expires_at)
                            if event.expires_at is not None
                            else None
                        ),
                    ),
                )
                event_id = int(cursor.lastrowid)

                connection.executemany(
                    """
                    INSERT INTO giveaway_codes (
                        event_id,
                        code,
                        reward_name,
                        reward_amount,
                        is_claimed,
                        claimed_by,
                        claimed_at
                    ) VALUES (?, ?, ?, ?, 0, NULL, NULL)
                    """,
                    [
                        (
                            event_id,
                            seed.code,
                            seed.reward_name,
                            seed.reward_amount,
                        )
                        for seed in code_seeds
                    ],
                )
                connection.commit()

        created = self._get_event_sync(event_id)
        if created is None:
            raise RuntimeError("Nao foi possivel recuperar o evento criado.")
        return created

    def _get_event_sync(self, event_id: int) -> GiveawayEvent | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        id,
                        title,
                        description,
                        channel_id,
                        message_id,
                        created_by,
                        created_at,
                        is_active,
                        max_redemptions,
                        total_codes,
                        notify_user_id,
                        embed_color,
                        expires_at
                    FROM giveaway_events
                    WHERE id = ?
                    """,
                    (event_id,),
                ).fetchone()
        return self._row_to_event(row) if row else None

    def _get_event_by_message_id_sync(self, message_id: int) -> GiveawayEvent | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        id,
                        title,
                        description,
                        channel_id,
                        message_id,
                        created_by,
                        created_at,
                        is_active,
                        max_redemptions,
                        total_codes,
                        notify_user_id,
                        embed_color,
                        expires_at
                    FROM giveaway_events
                    WHERE message_id = ?
                    """,
                    (message_id,),
                ).fetchone()
        return self._row_to_event(row) if row else None

    def _list_active_published_events_sync(self) -> list[GiveawayEvent]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute("""
                    SELECT
                        id,
                        title,
                        description,
                        channel_id,
                        message_id,
                        created_by,
                        created_at,
                        is_active,
                        max_redemptions,
                        total_codes,
                        notify_user_id,
                        embed_color,
                        expires_at
                    FROM giveaway_events
                    WHERE is_active = 1 AND message_id IS NOT NULL
                    ORDER BY created_at ASC
                    """).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _get_events_expiring_at_or_before_sync(
        self,
        moment: str,
    ) -> list[GiveawayEvent]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        title,
                        description,
                        channel_id,
                        message_id,
                        created_by,
                        created_at,
                        is_active,
                        max_redemptions,
                        total_codes,
                        notify_user_id,
                        embed_color,
                        expires_at
                    FROM giveaway_events
                    WHERE is_active = 1
                      AND message_id IS NOT NULL
                      AND expires_at IS NOT NULL
                      AND expires_at <= ?
                    ORDER BY expires_at ASC
                    """,
                    (moment,),
                ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _update_event_publication_sync(
        self,
        event_id: int,
        channel_id: int,
        message_id: int,
        embed_color: int | None,
        expires_at: str | None,
    ) -> GiveawayEvent:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE giveaway_events
                    SET channel_id = ?,
                        message_id = ?,
                        embed_color = COALESCE(?, embed_color),
                        expires_at = COALESCE(?, expires_at),
                        is_active = 1
                    WHERE id = ?
                    """,
                    (channel_id, message_id, embed_color, expires_at, event_id),
                )
                connection.commit()

        event = self._get_event_sync(event_id)
        if event is None:
            raise RuntimeError("Nao foi possivel atualizar o evento publicado.")
        return event

    def _set_event_active_sync(
        self,
        event_id: int,
        is_active: bool,
    ) -> GiveawayEvent | None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE giveaway_events
                    SET is_active = ?
                    WHERE id = ?
                    """,
                    (1 if is_active else 0, event_id),
                )
                connection.commit()
        return self._get_event_sync(event_id)

    def _get_event_stats_sync(self, event_id: int) -> GiveawayEventStats | None:
        with self._lock:
            if self._get_event_sync(event_id) is None:
                return None

            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total_codes,
                        SUM(CASE WHEN is_claimed = 1 THEN 1 ELSE 0 END)
                            AS claimed_codes,
                        SUM(
                            CASE
                                WHEN reward_name IS NOT NULL
                                  OR reward_amount IS NOT NULL
                                THEN 1
                                ELSE 0
                            END
                        ) AS rewarded_codes
                    FROM giveaway_codes
                    WHERE event_id = ?
                    """,
                    (event_id,),
                ).fetchone()
        if row is None:
            return None

        total_codes = int(row["total_codes"] or 0)
        claimed_codes = int(row["claimed_codes"] or 0)
        rewarded_codes = int(row["rewarded_codes"] or 0)
        return GiveawayEventStats(
            total_codes=total_codes,
            claimed_codes=claimed_codes,
            available_codes=total_codes - claimed_codes,
            rewarded_codes=rewarded_codes,
        )

    def _get_user_claim_sync(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayClaim | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        c.id AS claim_id,
                        c.event_id,
                        c.user_id,
                        c.code_id,
                        c.claimed_at,
                        c.reward_amount,
                        c.reward_name,
                        gc.code
                    FROM giveaway_claims AS c
                    INNER JOIN giveaway_codes AS gc ON gc.id = c.code_id
                    WHERE c.event_id = ? AND c.user_id = ?
                    ORDER BY c.claimed_at DESC, c.id DESC
                    LIMIT 1
                    """,
                    (event_id, user_id),
                ).fetchone()
        return self._row_to_claim(row) if row else None

    def _get_user_ticket_balance_sync(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayTicketBalance:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT extra_tickets
                    FROM giveaway_user_tickets
                    WHERE event_id = ? AND user_id = ?
                    """,
                    (event_id, user_id),
                ).fetchone()

        return GiveawayTicketBalance(
            event_id=event_id,
            user_id=user_id,
            extra_tickets=int(row["extra_tickets"]) if row else 0,
        )

    def _add_user_tickets_sync(
        self,
        event_id: int,
        user_id: int,
        amount: int,
    ) -> GiveawayTicketBalance:
        updated_at = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if self._get_event_row(connection, event_id) is None:
                    connection.rollback()
                    raise RuntimeError("Evento nao encontrado.")

                connection.execute(
                    """
                    INSERT INTO giveaway_user_tickets (
                        event_id,
                        user_id,
                        extra_tickets,
                        updated_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(event_id, user_id) DO UPDATE SET
                        extra_tickets = extra_tickets + excluded.extra_tickets,
                        updated_at = excluded.updated_at
                    """,
                    (event_id, user_id, amount, updated_at),
                )
                connection.commit()

        return self._get_user_ticket_balance_sync(event_id, user_id)

    def _remove_user_tickets_sync(
        self,
        event_id: int,
        user_id: int,
        amount: int,
    ) -> GiveawayTicketBalance:
        updated_at = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if self._get_event_row(connection, event_id) is None:
                    connection.rollback()
                    raise RuntimeError("Evento nao encontrado.")

                current = connection.execute(
                    """
                    SELECT extra_tickets
                    FROM giveaway_user_tickets
                    WHERE event_id = ? AND user_id = ?
                    """,
                    (event_id, user_id),
                ).fetchone()
                current_tickets = int(current["extra_tickets"]) if current else 0
                next_tickets = max(0, current_tickets - amount)

                connection.execute(
                    """
                    INSERT INTO giveaway_user_tickets (
                        event_id,
                        user_id,
                        extra_tickets,
                        updated_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(event_id, user_id) DO UPDATE SET
                        extra_tickets = excluded.extra_tickets,
                        updated_at = excluded.updated_at
                    """,
                    (event_id, user_id, next_tickets, updated_at),
                )
                connection.commit()

        return self._get_user_ticket_balance_sync(event_id, user_id)

    def _list_remaining_codes_sync(self, event_id: int) -> list[GiveawayCode]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        event_id,
                        code,
                        reward_name,
                        reward_amount,
                        is_claimed,
                        claimed_by,
                        claimed_at
                    FROM giveaway_codes
                    WHERE event_id = ? AND is_claimed = 0
                    ORDER BY
                        COALESCE(reward_amount, 0) DESC,
                        code ASC
                    """,
                    (event_id,),
                ).fetchall()
        return [self._row_to_code(row) for row in rows]

    def _list_remaining_rewarded_codes_sync(
        self,
        event_id: int,
    ) -> list[GiveawayCode]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        event_id,
                        code,
                        reward_name,
                        reward_amount,
                        is_claimed,
                        claimed_by,
                        claimed_at
                    FROM giveaway_codes
                    WHERE event_id = ?
                      AND is_claimed = 0
                      AND (
                          reward_name IS NOT NULL
                          OR reward_amount IS NOT NULL
                      )
                    ORDER BY
                        COALESCE(reward_amount, 0) DESC,
                        code ASC
                    """,
                    (event_id,),
                ).fetchall()
        return [self._row_to_code(row) for row in rows]

    def _list_winning_claims_sync(self, event_id: int) -> list[GiveawayClaim]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        c.id AS claim_id,
                        c.event_id,
                        c.user_id,
                        c.code_id,
                        c.claimed_at,
                        c.reward_amount,
                        c.reward_name,
                        gc.code
                    FROM giveaway_claims AS c
                    INNER JOIN giveaway_codes AS gc ON gc.id = c.code_id
                    WHERE c.event_id = ?
                      AND (
                          c.reward_name IS NOT NULL
                          OR c.reward_amount IS NOT NULL
                      )
                    ORDER BY c.claimed_at ASC
                    """,
                    (event_id,),
                ).fetchall()
        return [self._row_to_claim(row) for row in rows]

    @staticmethod
    def _get_event_row(
        connection: sqlite3.Connection,
        event_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                id,
                title,
                description,
                channel_id,
                message_id,
                created_by,
                created_at,
                is_active,
                max_redemptions,
                total_codes,
                notify_user_id,
                embed_color,
                expires_at
            FROM giveaway_events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()

    def _claim_next_available_code_sync(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayDrawResult:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")

                event_row = self._get_event_row(connection, event_id)
                if event_row is None:
                    connection.rollback()
                    return GiveawayDrawResult(
                        status=GiveawayDrawStatus.EVENT_NOT_FOUND,
                    )

                event = self._row_to_event(event_row)

                claims_row = connection.execute(
                    """
                    SELECT COUNT(*) AS claims_used
                    FROM giveaway_claims
                    WHERE event_id = ? AND user_id = ?
                    """,
                    (event_id, user_id),
                ).fetchone()
                claims_used = int(claims_row["claims_used"] or 0)

                tickets_row = connection.execute(
                    """
                    SELECT extra_tickets
                    FROM giveaway_user_tickets
                    WHERE event_id = ? AND user_id = ?
                    """,
                    (event_id, user_id),
                ).fetchone()
                extra_tickets = int(tickets_row["extra_tickets"]) if tickets_row else 0

                latest_claim_row = connection.execute(
                    """
                    SELECT
                        c.id AS claim_id,
                        c.event_id,
                        c.user_id,
                        c.code_id,
                        c.claimed_at,
                        c.reward_amount,
                        c.reward_name,
                        gc.code
                    FROM giveaway_claims AS c
                    INNER JOIN giveaway_codes AS gc ON gc.id = c.code_id
                    WHERE c.event_id = ? AND c.user_id = ?
                    ORDER BY c.claimed_at DESC, c.id DESC
                    LIMIT 1
                    """,
                    (event_id, user_id),
                ).fetchone()
                if claims_used > 0 and extra_tickets <= 0:
                    connection.rollback()
                    return GiveawayDrawResult(
                        status=GiveawayDrawStatus.ALREADY_CLAIMED,
                        event=event,
                        claim=(
                            self._row_to_claim(latest_claim_row)
                            if latest_claim_row
                            else None
                        ),
                        claims_used=claims_used,
                        extra_tickets_remaining=extra_tickets,
                    )

                if not event.is_active:
                    connection.rollback()
                    return GiveawayDrawResult(
                        status=GiveawayDrawStatus.EVENT_INACTIVE,
                        event=event,
                        claims_used=claims_used,
                        extra_tickets_remaining=extra_tickets,
                    )

                if event.expires_at is not None and event.expires_at <= utc_now():
                    connection.execute(
                        """
                        UPDATE giveaway_events
                        SET is_active = 0
                        WHERE id = ?
                        """,
                        (event_id,),
                    )
                    connection.commit()
                    return GiveawayDrawResult(
                        status=GiveawayDrawStatus.EVENT_INACTIVE,
                        event=replace(event, is_active=False),
                        claims_used=claims_used,
                        extra_tickets_remaining=extra_tickets,
                    )

                code_row = connection.execute(
                    """
                    SELECT
                        id,
                        event_id,
                        code,
                        reward_name,
                        reward_amount,
                        is_claimed,
                        claimed_by,
                        claimed_at
                    FROM giveaway_codes
                    WHERE event_id = ? AND is_claimed = 0
                    ORDER BY RANDOM()
                    LIMIT 1
                    """,
                    (event_id,),
                ).fetchone()
                if code_row is None:
                    connection.execute(
                        """
                        UPDATE giveaway_events
                        SET is_active = 0
                        WHERE id = ?
                        """,
                        (event_id,),
                    )
                    connection.commit()
                    return GiveawayDrawResult(
                        status=GiveawayDrawStatus.SOLD_OUT,
                        event=replace(event, is_active=False),
                        claims_used=claims_used,
                        extra_tickets_remaining=extra_tickets,
                    )

                claimed_at = serialize_datetime(utc_now())
                code = self._row_to_code(code_row)

                connection.execute(
                    """
                    UPDATE giveaway_codes
                    SET is_claimed = 1,
                        claimed_by = ?,
                        claimed_at = ?
                    WHERE id = ?
                    """,
                    (user_id, claimed_at, code.id),
                )

                claim_cursor = connection.execute(
                    """
                    INSERT INTO giveaway_claims (
                        event_id,
                        user_id,
                        code_id,
                        claimed_at,
                        reward_amount,
                        reward_name
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        user_id,
                        code.id,
                        claimed_at,
                        code.reward_amount,
                        code.reward_name,
                    ),
                )

                extra_tickets_remaining = extra_tickets
                if claims_used > 0:
                    extra_tickets_remaining = max(0, extra_tickets - 1)
                    connection.execute(
                        """
                        UPDATE giveaway_user_tickets
                        SET extra_tickets = ?,
                            updated_at = ?
                        WHERE event_id = ? AND user_id = ?
                        """,
                        (
                            extra_tickets_remaining,
                            claimed_at,
                            event_id,
                            user_id,
                        ),
                    )

                remaining = connection.execute(
                    """
                    SELECT 1
                    FROM giveaway_codes
                    WHERE event_id = ? AND is_claimed = 0
                    LIMIT 1
                    """,
                    (event_id,),
                ).fetchone()
                if remaining is None:
                    connection.execute(
                        """
                        UPDATE giveaway_events
                        SET is_active = 0
                        WHERE id = ?
                        """,
                        (event_id,),
                    )
                    event = replace(event, is_active=False)

                connection.commit()

                claim = GiveawayClaim(
                    id=int(claim_cursor.lastrowid),
                    event_id=event_id,
                    user_id=user_id,
                    code_id=code.id,
                    claimed_at=parse_datetime(claimed_at),
                    reward_amount=code.reward_amount,
                    reward_name=code.reward_name,
                    code=code.code,
                )
                code = replace(
                    code,
                    is_claimed=True,
                    claimed_by=user_id,
                    claimed_at=parse_datetime(claimed_at),
                )
                return GiveawayDrawResult(
                    status=GiveawayDrawStatus.SUCCESS,
                    event=event,
                    code=code,
                    claim=claim,
                    claims_used=claims_used + 1,
                    extra_tickets_remaining=extra_tickets_remaining,
                )

    def _finalize_event_sync(self, event_id: int) -> GiveawayFinalizationResult:
        remaining_codes = self._list_remaining_rewarded_codes_sync(event_id)
        winning_claims = self._list_winning_claims_sync(event_id)
        event = self._set_event_active_sync(event_id, is_active=False)
        if event is None:
            raise RuntimeError("Nao foi possivel finalizar o evento.")

        return GiveawayFinalizationResult(
            event=event,
            remaining_codes=remaining_codes,
            winning_claims=winning_claims,
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> GiveawayEvent:
        return GiveawayEvent(
            id=int(row["id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            channel_id=(
                int(row["channel_id"]) if row["channel_id"] is not None else None
            ),
            message_id=(
                int(row["message_id"]) if row["message_id"] is not None else None
            ),
            created_by=int(row["created_by"]),
            created_at=parse_datetime(str(row["created_at"])),
            is_active=bool(row["is_active"]),
            max_redemptions=(
                int(row["max_redemptions"])
                if row["max_redemptions"] is not None
                else None
            ),
            total_codes=int(row["total_codes"]),
            notify_user_id=(
                int(row["notify_user_id"])
                if row["notify_user_id"] is not None
                else None
            ),
            embed_color=(
                int(row["embed_color"]) if row["embed_color"] is not None else None
            ),
            expires_at=(
                parse_datetime(str(row["expires_at"]))
                if row["expires_at"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_claim(row: sqlite3.Row) -> GiveawayClaim:
        return GiveawayClaim(
            id=int(row["claim_id"]),
            event_id=int(row["event_id"]),
            user_id=int(row["user_id"]),
            code_id=int(row["code_id"]),
            claimed_at=parse_datetime(str(row["claimed_at"])),
            reward_amount=(
                int(row["reward_amount"]) if row["reward_amount"] is not None else None
            ),
            reward_name=(
                str(row["reward_name"]) if row["reward_name"] is not None else None
            ),
            code=str(row["code"]),
        )

    @staticmethod
    def _row_to_code(row: sqlite3.Row) -> GiveawayCode:
        return GiveawayCode(
            id=int(row["id"]),
            event_id=int(row["event_id"]),
            code=str(row["code"]),
            reward_name=(
                str(row["reward_name"]) if row["reward_name"] is not None else None
            ),
            reward_amount=(
                int(row["reward_amount"]) if row["reward_amount"] is not None else None
            ),
            is_claimed=bool(row["is_claimed"]),
            claimed_by=(
                int(row["claimed_by"]) if row["claimed_by"] is not None else None
            ),
            claimed_at=(
                parse_datetime(str(row["claimed_at"]))
                if row["claimed_at"] is not None
                else None
            ),
        )
