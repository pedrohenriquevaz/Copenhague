from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

from app.models.giveaway import serialize_datetime, utc_now
from app.models.uno import UnoActionType, UnoGameStatus, UnoSession


class UnoRepositoryProtocol(Protocol):
    async def create_game(self, session: UnoSession) -> UnoSession: ...

    async def update_game(self, session: UnoSession) -> UnoSession: ...

    async def get_game(self, game_id: int) -> UnoSession | None: ...

    async def get_game_by_message_id(self, message_id: int) -> UnoSession | None: ...

    async def list_active_games_for_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UnoSession]: ...

    async def get_active_game_for_channel(
        self,
        guild_id: int,
        channel_id: int,
    ) -> UnoSession | None: ...

    async def list_active_games(self) -> list[UnoSession]: ...

    async def record_action(
        self,
        *,
        game_id: int,
        user_id: int | None,
        action_type: UnoActionType,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    async def reset_user_profile(
        self, guild_id: int, user_id: int
    ) -> dict[str, int]: ...


class SQLiteUnoRepository:
    """Persistência das partidas multiplayer de UNO."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _initialize_schema(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS uno_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER,
                    status TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    player_ids_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT
                )
                """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS uno_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    user_id INTEGER,
                    action_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(game_id) REFERENCES uno_games(id)
                )
                """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_uno_games_guild_status
                ON uno_games(guild_id, status, updated_at)
                """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_uno_games_channel
                ON uno_games(guild_id, channel_id, status)
                """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_uno_games_message
                ON uno_games(message_id)
                """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_uno_actions_game
                ON uno_actions(game_id, created_at)
                """)

    async def create_game(self, session: UnoSession) -> UnoSession:
        return await asyncio.to_thread(self._create_game_sync, session)

    async def update_game(self, session: UnoSession) -> UnoSession:
        return await asyncio.to_thread(self._update_game_sync, session)

    async def get_game(self, game_id: int) -> UnoSession | None:
        return await asyncio.to_thread(self._get_game_sync, game_id)

    async def get_game_by_message_id(self, message_id: int) -> UnoSession | None:
        return await asyncio.to_thread(self._get_game_by_message_id_sync, message_id)

    async def list_active_games_for_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UnoSession]:
        return await asyncio.to_thread(
            self._list_active_games_for_user_sync,
            guild_id,
            user_id,
        )

    async def get_active_game_for_channel(
        self,
        guild_id: int,
        channel_id: int,
    ) -> UnoSession | None:
        return await asyncio.to_thread(
            self._get_active_game_for_channel_sync,
            guild_id,
            channel_id,
        )

    async def list_active_games(self) -> list[UnoSession]:
        return await asyncio.to_thread(self._list_active_games_sync)

    async def record_action(
        self,
        *,
        game_id: int,
        user_id: int | None,
        action_type: UnoActionType,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_action_sync,
            game_id,
            user_id,
            action_type,
            metadata or {},
        )

    async def reset_user_profile(self, guild_id: int, user_id: int) -> dict[str, int]:
        games = await self.list_active_games_for_user(guild_id, user_id)
        return {"active_uno_games": len(games)}

    def _create_game_sync(self, session: UnoSession) -> UnoSession:
        now = utc_now()
        session.created_at = now
        session.updated_at = now
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO uno_games (
                    guild_id, channel_id, message_id, status, created_by,
                    player_ids_json, snapshot_json, created_at, updated_at,
                    finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._game_params(session),
            )
            session.id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE uno_games SET snapshot_json = ? WHERE id = ?",
                (self._snapshot(session), session.id),
            )
        created = self._get_game_sync(session.id)
        if created is None:
            raise RuntimeError("Não foi possível criar a partida de UNO.")
        return created

    def _update_game_sync(self, session: UnoSession) -> UnoSession:
        if session.id is None:
            raise ValueError("Partida sem ID não pode ser atualizada.")
        session.updated_at = utc_now()
        if session.status in {UnoGameStatus.FINISHED, UnoGameStatus.CANCELLED}:
            session.finished_at = session.finished_at or session.updated_at
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE uno_games
                SET guild_id = ?, channel_id = ?, message_id = ?, status = ?,
                    created_by = ?, player_ids_json = ?, snapshot_json = ?,
                    created_at = ?, updated_at = ?, finished_at = ?
                WHERE id = ?
                """,
                (*self._game_params(session), session.id),
            )
            if cursor.rowcount == 0:
                raise ValueError("Partida de UNO não encontrada.")
        updated = self._get_game_sync(session.id)
        if updated is None:
            raise RuntimeError("Não foi possível recuperar a partida de UNO.")
        return updated

    def _get_game_sync(self, game_id: int) -> UnoSession | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM uno_games WHERE id = ?",
                (game_id,),
            ).fetchone()
        return self._row_to_game(row) if row else None

    def _get_game_by_message_id_sync(self, message_id: int) -> UnoSession | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM uno_games
                WHERE message_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (message_id,),
            ).fetchone()
        return self._row_to_game(row) if row else None

    def _list_active_games_for_user_sync(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UnoSession]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM uno_games
                WHERE guild_id = ?
                  AND status IN ('LOBBY', 'PLAYING')
                  AND player_ids_json LIKE ?
                ORDER BY updated_at DESC
                """,
                (guild_id, f"%{user_id}%"),
            ).fetchall()
        games = [self._row_to_game(row) for row in rows]
        return [game for game in games if user_id in game.player_ids]

    def _get_active_game_for_channel_sync(
        self,
        guild_id: int,
        channel_id: int,
    ) -> UnoSession | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM uno_games
                WHERE guild_id = ? AND channel_id = ?
                  AND status IN ('LOBBY', 'PLAYING')
                ORDER BY updated_at DESC LIMIT 1
                """,
                (guild_id, channel_id),
            ).fetchone()
        return self._row_to_game(row) if row else None

    def _list_active_games_sync(self) -> list[UnoSession]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM uno_games
                WHERE status IN ('LOBBY', 'PLAYING')
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._row_to_game(row) for row in rows]

    def _record_action_sync(
        self,
        game_id: int,
        user_id: int | None,
        action_type: UnoActionType,
        metadata: dict[str, Any],
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO uno_actions (
                    game_id, user_id, action_type, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    user_id,
                    action_type.value,
                    json.dumps(metadata, ensure_ascii=False),
                    serialize_datetime(utc_now()),
                ),
            )

    def _game_params(self, session: UnoSession) -> tuple[Any, ...]:
        return (
            session.guild_id,
            session.channel_id,
            session.message_id,
            session.status.value,
            session.created_by,
            json.dumps(session.player_ids),
            self._snapshot(session),
            serialize_datetime(session.created_at or utc_now()),
            serialize_datetime(session.updated_at or utc_now()),
            serialize_datetime(session.finished_at) if session.finished_at else None,
        )

    @staticmethod
    def _snapshot(session: UnoSession) -> str:
        return json.dumps(session.to_dict(), ensure_ascii=False)

    @staticmethod
    def _row_to_game(row: Any) -> UnoSession:
        data = json.loads(str(row["snapshot_json"]))
        data["id"] = int(row["id"])
        data["message_id"] = row["message_id"]
        data["status"] = str(row["status"])
        data["updated_at"] = row["updated_at"]
        data["finished_at"] = row["finished_at"]
        return UnoSession.from_dict(data)
