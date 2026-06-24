from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import Protocol

from app.models.bolao import (
    BolaoEvent,
    BolaoEventCreate,
    BolaoGuess,
    BolaoGuessResult,
    BolaoGuessStatus,
)
from app.models.giveaway import parse_datetime, serialize_datetime, utc_now


class BolaoRepositoryProtocol(Protocol):
    """Contrato de persistencia esperado pelo service de bolao."""

    async def create_event(self, event: BolaoEventCreate) -> BolaoEvent: ...

    async def publish_event(
        self,
        bolao_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> BolaoEvent: ...

    async def get_event(self, bolao_id: int) -> BolaoEvent | None: ...

    async def get_event_by_message_id(self, message_id: int) -> BolaoEvent | None: ...

    async def list_active_events(self) -> list[BolaoEvent]: ...

    async def close_event(self, bolao_id: int) -> BolaoEvent | None: ...

    async def create_guess(
        self,
        bolao_id: int,
        user_id: int,
        score_team_1: int,
        score_team_2: int,
    ) -> BolaoGuessResult: ...


class SQLiteBolaoRepository:
    """Persistencia SQLite para boloes e palpites."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize_schema()

    async def create_event(self, event: BolaoEventCreate) -> BolaoEvent:
        return await asyncio.to_thread(self._create_event_sync, event)

    async def publish_event(
        self,
        bolao_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> BolaoEvent:
        return await asyncio.to_thread(
            self._publish_event_sync,
            bolao_id,
            channel_id,
            message_id,
        )

    async def get_event(self, bolao_id: int) -> BolaoEvent | None:
        return await asyncio.to_thread(self._get_event_sync, bolao_id)

    async def get_event_by_message_id(self, message_id: int) -> BolaoEvent | None:
        return await asyncio.to_thread(self._get_event_by_message_id_sync, message_id)

    async def list_active_events(self) -> list[BolaoEvent]:
        return await asyncio.to_thread(self._list_active_events_sync)

    async def close_event(self, bolao_id: int) -> BolaoEvent | None:
        return await asyncio.to_thread(self._close_event_sync, bolao_id)

    async def create_guess(
        self,
        bolao_id: int,
        user_id: int,
        score_team_1: int,
        score_team_2: int,
    ) -> BolaoGuessResult:
        return await asyncio.to_thread(
            self._create_guess_sync,
            bolao_id,
            user_id,
            score_team_1,
            score_team_2,
        )

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
                    CREATE TABLE IF NOT EXISTS bolao_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        prize TEXT NOT NULL,
                        team_1 TEXT NOT NULL,
                        team_2 TEXT NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        created_by INTEGER NOT NULL,
                        receiver_user_id INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS bolao_guesses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bolao_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        score_team_1 INTEGER NOT NULL,
                        score_team_2 INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(bolao_id) REFERENCES bolao_events(id)
                            ON DELETE CASCADE,
                        UNIQUE(bolao_id, user_id)
                    )
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bolao_events_active
                    ON bolao_events(is_active, created_at)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bolao_guesses_event_user
                    ON bolao_guesses(bolao_id, user_id)
                    """)

    def _create_event_sync(self, event: BolaoEventCreate) -> BolaoEvent:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT INTO bolao_events (
                        title,
                        description,
                        prize,
                        team_1,
                        team_2,
                        channel_id,
                        message_id,
                        created_by,
                        receiver_user_id,
                        created_at,
                        is_active
                    ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, 1)
                    """,
                    (
                        event.title,
                        event.description,
                        event.prize,
                        event.team_1,
                        event.team_2,
                        event.created_by,
                        event.receiver_user_id,
                        serialize_datetime(event.created_at),
                    ),
                )
                bolao_id = int(cursor.lastrowid)
                connection.commit()

        created = self._get_event_sync(bolao_id)
        if created is None:
            raise RuntimeError("Nao foi possivel recuperar o bolao criado.")
        return created

    def _publish_event_sync(
        self,
        bolao_id: int,
        channel_id: int,
        message_id: int,
    ) -> BolaoEvent:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE bolao_events
                    SET channel_id = ?,
                        message_id = ?
                    WHERE id = ?
                    """,
                    (channel_id, message_id, bolao_id),
                )
                connection.commit()

        event = self._get_event_sync(bolao_id)
        if event is None:
            raise RuntimeError("Nao foi possivel publicar o bolao.")
        return event

    def _get_event_sync(self, bolao_id: int) -> BolaoEvent | None:
        with self._lock:
            with self._connect() as connection:
                row = self._get_event_row(connection, bolao_id)
        return self._row_to_event(row) if row else None

    def _get_event_by_message_id_sync(self, message_id: int) -> BolaoEvent | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        id,
                        title,
                        description,
                        prize,
                        team_1,
                        team_2,
                        channel_id,
                        message_id,
                        created_by,
                        receiver_user_id,
                        created_at,
                        is_active
                    FROM bolao_events
                    WHERE message_id = ?
                    """,
                    (message_id,),
                ).fetchone()
        return self._row_to_event(row) if row else None

    def _list_active_events_sync(self) -> list[BolaoEvent]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute("""
                    SELECT
                        id,
                        title,
                        description,
                        prize,
                        team_1,
                        team_2,
                        channel_id,
                        message_id,
                        created_by,
                        receiver_user_id,
                        created_at,
                        is_active
                    FROM bolao_events
                    WHERE is_active = 1
                    ORDER BY created_at DESC
                    """).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _close_event_sync(self, bolao_id: int) -> BolaoEvent | None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_event_row(connection, bolao_id)
                if row is None:
                    connection.rollback()
                    return None

                connection.execute(
                    """
                    UPDATE bolao_events
                    SET is_active = 0
                    WHERE id = ?
                    """,
                    (bolao_id,),
                )
                connection.commit()

        return self._get_event_sync(bolao_id)

    def _create_guess_sync(
        self,
        bolao_id: int,
        user_id: int,
        score_team_1: int,
        score_team_2: int,
    ) -> BolaoGuessResult:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                event_row = self._get_event_row(connection, bolao_id)
                if event_row is None:
                    connection.rollback()
                    return BolaoGuessResult(status=BolaoGuessStatus.EVENT_NOT_FOUND)

                event = self._row_to_event(event_row)
                existing_row = self._get_guess_row(connection, bolao_id, user_id)
                if existing_row is not None:
                    connection.rollback()
                    return BolaoGuessResult(
                        status=BolaoGuessStatus.ALREADY_GUESSED,
                        event=event,
                        guess=self._row_to_guess(existing_row),
                    )

                if not event.is_active:
                    connection.rollback()
                    return BolaoGuessResult(
                        status=BolaoGuessStatus.EVENT_CLOSED,
                        event=event,
                    )

                created_at = serialize_datetime(utc_now())
                cursor = connection.execute(
                    """
                    INSERT INTO bolao_guesses (
                        bolao_id,
                        user_id,
                        score_team_1,
                        score_team_2,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        bolao_id,
                        user_id,
                        score_team_1,
                        score_team_2,
                        created_at,
                    ),
                )
                connection.commit()

        guess = BolaoGuess(
            id=int(cursor.lastrowid),
            bolao_id=bolao_id,
            user_id=user_id,
            score_team_1=score_team_1,
            score_team_2=score_team_2,
            created_at=parse_datetime(created_at),
        )
        return BolaoGuessResult(
            status=BolaoGuessStatus.SUCCESS,
            event=event,
            guess=guess,
        )

    @staticmethod
    def _get_event_row(
        connection: sqlite3.Connection,
        bolao_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                id,
                title,
                description,
                prize,
                team_1,
                team_2,
                channel_id,
                message_id,
                created_by,
                receiver_user_id,
                created_at,
                is_active
            FROM bolao_events
            WHERE id = ?
            """,
            (bolao_id,),
        ).fetchone()

    @staticmethod
    def _get_guess_row(
        connection: sqlite3.Connection,
        bolao_id: int,
        user_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                id,
                bolao_id,
                user_id,
                score_team_1,
                score_team_2,
                created_at
            FROM bolao_guesses
            WHERE bolao_id = ? AND user_id = ?
            """,
            (bolao_id, user_id),
        ).fetchone()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> BolaoEvent:
        return BolaoEvent(
            id=int(row["id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            prize=str(row["prize"]),
            team_1=str(row["team_1"]),
            team_2=str(row["team_2"]),
            channel_id=(
                int(row["channel_id"]) if row["channel_id"] is not None else None
            ),
            message_id=(
                int(row["message_id"]) if row["message_id"] is not None else None
            ),
            created_by=int(row["created_by"]),
            receiver_user_id=int(row["receiver_user_id"]),
            created_at=parse_datetime(str(row["created_at"])),
            is_active=bool(row["is_active"]),
        )

    @staticmethod
    def _row_to_guess(row: sqlite3.Row) -> BolaoGuess:
        return BolaoGuess(
            id=int(row["id"]),
            bolao_id=int(row["bolao_id"]),
            user_id=int(row["user_id"]),
            score_team_1=int(row["score_team_1"]),
            score_team_2=int(row["score_team_2"]),
            created_at=parse_datetime(str(row["created_at"])),
        )
